"""Qwen3-TTS en temps réel : une trame de son (80 ms) = un seul graphe CUDA rejoué.

Le `generate()` d'origine lance ~8 000 petites opérations par trame depuis Python : la carte attend le processeur
(0,37 s de calcul sur 4,5 s). Ici la boucle du locuteur (« talker », 28 couches) et celle du prédicteur de codes
(5 couches, 15 pas) sont réécrites avec des caches statiques, puis gravées une fois dans un graphe CUDA : chaque
trame est un seul `replay()` et une seule synchronisation (le test de fin). Même modèle, même tirage (température,
top-k, pénalité de répétition, jetons interdits) : seul le coût de lancement disparaît.

    from graphe import accelerer ; accelerer(modele)   # modele = Qwen3TTSModel sur cuda, lot de 1
"""
from types import SimpleNamespace

import numpy as np

import torch
from transformers import StaticCache

LONGUEUR_MAX = 1024          # invite (référence ~9 s + texte) + trames générées (1 trame = 80 ms) : ~60 s par phrase


def _tirer(logits, top_k, temperature):
    logits = logits / temperature
    seuil = torch.topk(logits, top_k).values[..., -1:]
    logits = logits.masked_fill(logits < seuil, float("-inf"))
    return torch.multinomial(logits.softmax(-1), 1)


class TrameGraphee:
    def __init__(self, modele_tts):
        self.m = modele_tts.model
        self.talker = self.m.talker
        self.cp = self.talker.code_predictor
        tc = self.talker.config
        self.dev = next(self.talker.parameters()).device
        self.dtype = next(self.talker.parameters()).dtype
        self.eos = tc.codec_eos_token_id
        self.vocab = tc.vocab_size
        self.groupes = tc.num_code_groups
        self.H = tc.hidden_size
        d, dt = self.dev, self.dtype
        self.cache = StaticCache(config=self.talker.config, max_cache_len=LONGUEUR_MAX)
        self.cache_cp = StaticCache(config=self.cp.config, max_cache_len=self.groupes + 1)
        self.arange = torch.arange(LONGUEUR_MAX, device=d)
        # masques du prédicteur : constants (2 positions au départ, puis une par pas)
        n = self.groupes + 1
        tri = torch.ones(2, n, dtype=torch.bool, device=d).tril()
        self.masque_cp0 = tri.view(1, 1, 2, n)
        self.masques_cp = [(torch.arange(n, device=d) <= p).view(1, 1, 1, n) for p in range(2, n)]
        # entrées / sorties statiques du graphe
        self.jeton = torch.zeros(1, 1, dtype=torch.long, device=d)
        self.cache_pos = torch.zeros(1, dtype=torch.long, device=d)
        self.rope_delta = torch.zeros(1, dtype=torch.long, device=d)
        self.passe = torch.zeros(1, 1, self.H, dtype=dt, device=d)        # dernier état caché du talker
        self.texte = torch.zeros(1, 1, self.H, dtype=dt, device=d)        # texte restant (ou tts_pad) à ajouter
        self.vus = torch.zeros(1, self.vocab, dtype=torch.bool, device=d)  # pénalité de répétition
        self.interdits = torch.zeros(1, self.vocab, dtype=torch.bool, device=d)
        self.eos_permis = torch.ones(1, 1, dtype=torch.bool, device=d)
        self.codes = torch.zeros(1, self.groupes, dtype=torch.long, device=d)
        self.suivant = torch.zeros(1, 1, dtype=torch.long, device=d)
        self.graphe = None
        self.reglages = None

    # --- une trame, écrite pour être gravée : rien que des opérations sur tenseurs à forme fixe ---
    def _trame(self):
        top_k, temp, rep, sk, st = self.reglages
        emb_jeton = self.talker.get_input_embeddings()(self.jeton)                     # [1,1,H]
        # le prédicteur : 15 codes de plus pour cette trame
        x = self.cp.small_to_mtp_projection(torch.cat((self.passe, emb_jeton), dim=1))
        pos = torch.arange(2, device=self.dev)
        h = self.cp.model(inputs_embeds=x, attention_mask={"full_attention": self.masque_cp0}, position_ids=pos.view(1, -1),
                          past_key_values=self.cache_cp, use_cache=True, cache_position=pos).last_hidden_state
        code = _tirer(self.cp.lm_head[0](h[:, -1]), sk, st)
        codes, somme = [code], emb_jeton + self.cp.get_input_embeddings()[0](code)
        for i in range(1, self.groupes - 1):
            p = torch.full((1,), i + 1, dtype=torch.long, device=self.dev)
            e = self.cp.small_to_mtp_projection(self.cp.get_input_embeddings()[i - 1](code))
            h = self.cp.model(inputs_embeds=e, attention_mask={"full_attention": self.masques_cp[i - 1]}, position_ids=p.view(1, 1),
                              past_key_values=self.cache_cp, use_cache=True, cache_position=p).last_hidden_state
            code = _tirer(self.cp.lm_head[i](h[:, -1]), sk, st)
            codes.append(code)
            somme = somme + self.cp.get_input_embeddings()[i](code)
        self.codes.copy_(torch.cat([self.jeton] + codes, dim=-1))
        # le talker : un pas
        entree = somme + self.texte
        posr = (self.cache_pos + self.rope_delta).view(1, 1, 1).expand(3, 1, 1)
        masque = (self.arange <= self.cache_pos).view(1, 1, 1, -1)
        h = self.talker.model(inputs_embeds=entree, attention_mask=masque, position_ids=posr, past_key_values=self.cache,
                              use_cache=True, cache_position=self.cache_pos).last_hidden_state
        self.passe.copy_(h[:, -1:])
        logits = self.talker.codec_head(h[:, -1]).float()
        logits = torch.where(self.vus, torch.where(logits < 0, logits * rep, logits / rep), logits)
        logits = logits.masked_fill(self.interdits, float("-inf"))
        logits[:, self.eos] = torch.where(self.eos_permis[:, 0], logits[:, self.eos], torch.full_like(logits[:, self.eos], float("-inf")))
        jeton = _tirer(logits, top_k, temp)
        self.vus.scatter_(1, jeton, True)
        self.suivant.copy_(jeton)

    def _graver(self):
        s = torch.cuda.Stream()
        s.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(s):
            for _ in range(2):
                self._trame()
        torch.cuda.current_stream().wait_stream(s)
        self.graphe = torch.cuda.CUDAGraph()
        with torch.cuda.graph(self.graphe):
            self._trame()

    @torch.inference_mode()
    def generer(self, inputs_embeds, attention_mask, trailing_text_hidden, tts_pad_embed, max_new_tokens=2048,
                min_new_tokens=2, do_sample=True, top_k=50, top_p=1.0, temperature=0.9, subtalker_dosample=True,
                subtalker_top_k=50, subtalker_top_p=1.0, subtalker_temperature=0.9, eos_token_id=None,
                repetition_penalty=1.05, suppress_tokens=(), **_):
        assert inputs_embeds.shape[0] == 1, "lot de 1 seulement"
        reglages = (int(top_k), float(temperature), float(repetition_penalty), int(subtalker_top_k), float(subtalker_temperature))
        if self.reglages is not None and reglages != self.reglages:
            self.graphe = None                     # autres réglages de tirage : on regrave
        self.reglages = reglages
        L = inputs_embeds.shape[1]
        max_new_tokens = min(int(max_new_tokens), LONGUEUR_MAX - L - 1)
        # l'invite, sans graphe (sa longueur change à chaque phrase)
        position_ids, rope_deltas = self.talker.get_rope_index(attention_mask)
        rope_deltas = rope_deltas - (1 - attention_mask).sum(dim=-1).unsqueeze(1)
        pos = torch.arange(L, device=self.dev)
        masque = (self.arange.view(1, -1) <= pos.view(-1, 1)).view(1, 1, L, LONGUEUR_MAX)
        h = self.talker.model(inputs_embeds=inputs_embeds, attention_mask=masque, position_ids=position_ids,
                              past_key_values=self.cache, use_cache=True, cache_position=pos).last_hidden_state
        self.passe.copy_(h[:, -1:])
        self.interdits.zero_()
        if len(suppress_tokens):
            self.interdits[0, torch.tensor(list(suppress_tokens), device=self.dev)] = True
        self.vus.zero_()
        logits = self.talker.codec_head(h[:, -1]).float().masked_fill(self.interdits, float("-inf"))
        logits[:, self.eos] = float("-inf")                                  # min_new_tokens
        premier = _tirer(logits, reglages[0], reglages[1])
        self.vus.scatter_(1, premier, True)
        self.jeton.copy_(premier)
        self.rope_delta.copy_(rope_deltas.view(-1)[:1])
        if self.graphe is None:
            self.cache_pos.fill_(L)
            self.texte.copy_(tts_pad_embed.view(1, 1, -1))
            self._graver()
            # la gravure a joué des trames à blanc : on repart de l'invite (le cache au-delà de L est masqué)
            self.jeton.copy_(premier)
            self.passe.copy_(h[:, -1:])
            self.vus.zero_(); self.vus.scatter_(1, premier, True)
        trames, T = [], trailing_text_hidden.shape[1]
        for k in range(max_new_tokens):
            self.cache_pos.fill_(L + k)
            self.texte.copy_(trailing_text_hidden[:, k:k + 1] if k < T else tts_pad_embed.view(1, 1, -1))
            self.eos_permis.fill_(k + 1 >= min_new_tokens)
            self.graphe.replay()
            trames.append(self.codes.clone())
            self.jeton.copy_(self.suivant)
            if int(self.suivant.item()) == self.eos:
                break
        vide = torch.zeros(1, 1, self.H, dtype=self.dtype, device=self.dev)
        etats = [((vide,), None)] + [((vide,), c) for c in trames]
        return SimpleNamespace(hidden_states=etats)


def alleger_decodage(modele_tts, contexte: int = 25):
    """En clonage, qwen-tts redécode à chaque phrase TOUTE la référence (≈ 110 trames pour 9 s) devant les trames
    nouvelles, puis la coupe : du temps, et surtout un pic de mémoire vidéo à chaque phrase (le 19/09, ce pic poussait
    le cerveau hors de la carte). On ne décode que les `contexte` dernières trames de la référence (le raccord), et on
    remet des zéros devant pour que la coupe faite ensuite par qwen-tts tombe au même endroit."""
    tok = modele_tts.model.speech_tokenizer
    origine = tok.decode

    def decoder(entrees):
        entrees = list(entrees)
        longueurs = [int(e["audio_codes"].shape[0]) for e in entrees]
        gardees, retirees = [], []
        for e, n in zip(entrees, longueurs):
            r = max(0, n - contexte - _trames_nouvelles.get("n", n))
            retirees.append(r)
            gardees.append({"audio_codes": e["audio_codes"][r:]})
        wavs, fs = origine(gardees)
        sortie = []
        for w, n, r in zip(wavs, longueurs, retirees):
            if r:
                par_trame = len(w) / (n - r)
                w = np.concatenate([np.zeros(int(round(r * par_trame)), dtype=w.dtype), w])
            sortie.append(w)
        return sortie, fs

    tok.decode = decoder


_trames_nouvelles = {}


class _TableSurProcesseur(torch.nn.Module):
    """La table des mots du texte (151 936 × 2 048, 594 Mo) : une simple recherche par phrase, faite en mémoire système."""

    def __init__(self, table):
        super().__init__()
        self.poids = table.weight.detach().to("cpu")

    def forward(self, ids):
        return torch.nn.functional.embedding(ids.to("cpu"), self.poids).to(ids.device, non_blocking=True)


def charger_leger(Qwen3TTSModel, chemin):
    """Charge le modèle sur le processeur, garde la table du texte en mémoire système, puis envoie le reste sur la
    carte. Dans cet ordre-là seulement : retirée après coup, la table laissait un trou de 761 Mo que la carte ne
    pouvait pas rendre (même bloc que les autres poids)."""
    modele = Qwen3TTSModel.from_pretrained(chemin, device_map="cpu", dtype=torch.bfloat16)
    talker = modele.model.talker
    talker.model.text_embedding = _TableSurProcesseur(talker.model.text_embedding)
    modele.model.to("cuda")
    modele.device = torch.device("cuda")
    tok = modele.model.speech_tokenizer                   # pas un sous-module : il ne suit pas .to()
    tok.model.to("cuda")
    tok.device = torch.device("cuda")
    return modele


def alleger_memoire(modele_tts):
    """L'encodeur audio et l'encodeur de locuteur ne servent qu'à lire la référence : hors de la carte ensuite
    (appeler après create_voice_clone_prompt)."""
    modele_tts.model.speech_tokenizer.model.encoder.to("cpu")
    if getattr(modele_tts.model, "speaker_encoder", None) is not None:
        modele_tts.model.speaker_encoder.to("cpu")
    torch.cuda.empty_cache()


def accelerer(modele_tts):
    t = TrameGraphee(modele_tts)

    def generer(*a, **k):
        r = t.generer(*a, **k)
        _trames_nouvelles["n"] = len(r.hidden_states) - 1        # pour alleger_decodage : ce qui est vraiment neuf
        return r

    modele_tts.model.talker.generate = generer
    alleger_decodage(modele_tts)
    return t
