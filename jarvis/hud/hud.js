// Le HUD « salle de briefing » : événements du serveur (WebSocket /events), transcription écrite au rythme de la
// voix, journal des outils, panneaux holographiques, barre d'état, saisie, micro du navigateur, raccourcis.
import { creerReacteur } from "./reacteur.js";
import { creerPanneaux } from "./panneaux.js";

const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const transcription = $("transcription"), journalOutils = $("outils");

// ====================================================================== le réacteur (ou son remplaçant sans WebGL)
let reacteur = creerReacteur($("scene"));
if (!reacteur) {
  document.body.classList.add("sans3d");
  const rappels = [];
  (function boucle(t) { requestAnimationFrame(boucle); rappels.forEach(f => f(0.016, t)); })(performance.now());
  reacteur = { etat() {}, niveau() {}, micro() {}, decaler() {}, discret() {}, erreurLongue() {}, decompte() {}, finDecompte() {},
    surImage: f => rappels.push(f),
    estSur: () => false, rayonEcran: () => innerHeight * 0.17, centreEcran: () => ({ x: innerWidth / 2, y: innerHeight * 0.46 }),
    stats: () => ({}), mesurer: async () => ({}), carte: () => "aucune (WebGL indisponible)" };
}

const LIBELLES = { repos: "en veille", ecoute: "écoute", reflexion: "réflexion", parole: "parole", erreur: "erreur" };
let etatActuel = "repos";
function etat(nom) {
  document.body.classList.remove(etatActuel);
  etatActuel = nom;
  document.body.classList.add(nom);
  $("mode").textContent = LIBELLES[nom] || nom;
  reacteur.etat(nom);
  if (nom === "erreur") setTimeout(() => { if (etatActuel === "erreur") etat("repos"); }, 1300);
}

// le libellé suit le réacteur (qui glisse quand des panneaux s'ouvrent)
let compteImages = 0;
reacteur.surImage(() => {
  if (compteImages++ % 4) return;
  const c = reacteur.centreEcran(), r = reacteur.rayonEcran();
  $("mode").style.left = c.x + "px";
  $("mode").style.top = (c.y + r * 1.02) + "px";
});

// ====================================================================== horloge et démarrage
function horloge() {
  const d = new Date();
  $("horloge").firstChild.textContent = d.toLocaleTimeString("fr");
  $("date").textContent = d.toLocaleDateString("fr", { weekday: "long", day: "numeric", month: "long" });
}
horloge(); setInterval(horloge, 500);
if (!params.get("boot")) setTimeout(() => $("boot").classList.add("fini"), 1700);

// ====================================================================== les panneaux
const voile = $("voile"), voileImg = voile.querySelector("img");
function agrandir(url) { voileImg.src = url; voile.classList.add("visible"); }
voile.onclick = () => voile.classList.remove("visible");

const panneaux = creerPanneaux($("panneaux"), { agrandir, surChangement: recentrer });
function recentrer(nombre) {
  // le réacteur glisse au milieu de l'espace libre entre la transcription et les panneaux
  if (!nombre || document.body.classList.contains("discret")) { reacteur.decaler(0); return; }
  const zone = $("panneaux").getBoundingClientRect(), gauche = $("gauche").getBoundingClientRect();
  const libre = (gauche.right + zone.left) / 2;
  reacteur.decaler(Math.max(0, innerWidth / 2 - libre), (zone.left - gauche.right) / 2 - 12);
}
addEventListener("resize", () => recentrer(panneaux.nombre));

const imagesSession = [];
function ouvrirImage(url, legende, titre) {
  imagesSession.unshift({ url, legende });
  imagesSession.splice(4);
  panneaux.ouvrir({ genre: "images", titre, images: imagesSession.slice(0, imagesSession.length > 1 ? 4 : 1) });
}

// ====================================================================== transcription écrite au rythme de la voix
// Les jetons du cerveau arrivent plus vite qu'on ne parle : ils sont gardés de côté. Chaque phrase dite arrive
// avec sa durée (événement « phrase », émis au début de sa lecture) et s'écrit lettre à lettre sur cette durée.
// Voix coupée (« silence ») ou voix en panne : le texte s'affiche tel qu'il vient.
const prises = new Map();
let voixMuette = false, dernierePrise = null, derniereQuestion = "", echanges = 0;

function ajouter(el, conteneur, max) {
  conteneur.appendChild(el);
  while (conteneur.children.length > max) conteneur.removeChild(conteneur.firstChild);
  return el;
}
function ligneMoi(texte) {
  if (!texte || texte === derniereQuestion) return;
  derniereQuestion = texte;
  const p = document.createElement("p"); p.className = "moi"; p.textContent = texte;
  ajouter(p, transcription, 14);
  $("compte-echanges").textContent = String(++echanges).padStart(2, "0");
}
function note(texte) { const p = document.createElement("p"); p.className = "note"; p.textContent = texte; ajouter(p, transcription, 14); }

function prise(n) {
  let p = prises.get(n);
  if (!p) {
    const el = document.createElement("p"); el.className = "jarvis en-cours";
    ajouter(el, transcription, 14);
    p = { el, brut: "", dit: "", courante: null, parle: false, revele: false, complete: "", minuteur: null };
    prises.set(n, p);
    if (prises.size > 30) prises.delete(prises.keys().next().value);
  }
  dernierePrise = p;
  return p;
}
function joindre(a, b) { return a ? (b ? a + " " + b : a) : (b || ""); }
function afficher(p, texte) {
  p.el.textContent = texte;
  if (p === dernierePrise) $("discret-texte").querySelector("span").textContent = texte;
}
function terminerPhrase(p) {
  if (!p.courante) return;
  p.dit = joindre(p.dit, p.courante.texte);
  p.courante = null;
  afficher(p, p.dit);
}
function reveler(p) {
  if (p.parle) return;
  p.revele = true;
  afficher(p, (p.complete || p.brut).trim());
}
reacteur.surImage(() => {
  const maintenant = performance.now();
  for (const p of prises.values()) {
    if (!p.courante) continue;
    const c = p.courante, k = (maintenant - c.debut) / (c.duree * 1000);
    if (k >= 1) { terminerPhrase(p); continue; }
    const n = Math.max(1, Math.ceil(c.texte.length * k));
    if (n !== c.n) { c.n = n; afficher(p, joindre(p.dit, c.texte.slice(0, n))); }
  }
});

function surJeton(e) {
  const p = prise(e.prise);
  p.brut += e.texte;
  if (voixMuette || p.revele) afficher(p, p.brut.trimStart());
}
function surPhrase(e) {
  const p = prise(e.prise);
  if (p.revele) return;                               // déjà affichée en entier (voix trop lente à venir)
  p.parle = true; clearTimeout(p.minuteur);
  terminerPhrase(p);
  const texte = e.texte.trim();
  p.courante = { texte, duree: Math.max(0.25, e.duree || texte.length * 0.065), debut: performance.now(), n: 0 };
}
function surReponseComplete(e) {
  const p = prise(e.prise);
  p.complete = e.texte || p.brut;
  if (voixMuette) { reveler(p); p.el.classList.remove("en-cours"); return; }
  // aucune phrase dite six secondes après la fin de la réponse : la voix ne viendra pas
  if (!p.parle) p.minuteur = setTimeout(() => { if (!p.parle) { reveler(p); p.el.classList.remove("en-cours"); } }, 6000);
}
function surParoleFin(e) {
  const p = prises.get(e.prise); if (!p) return;
  terminerPhrase(p);
  if (!p.dit && !p.revele) reveler(p);
  p.el.classList.remove("en-cours");
}
function surInterruption() {
  for (const p of prises.values()) {
    if (!p.courante) continue;
    p.dit = joindre(p.dit, p.courante.texte.slice(0, p.courante.n) + "…");
    p.courante = null; afficher(p, p.dit); p.el.classList.remove("en-cours");
  }
}

// ====================================================================== le journal des outils
let appelsOutils = 0;
function outilAppel(e) {
  const d = document.createElement("div"); d.className = "outil en-cours"; d.dataset.outil = e.outil;
  const b = document.createElement("b"); b.textContent = e.outil; d.appendChild(b);
  const args = e.arguments && Object.keys(e.arguments).length ? Object.values(e.arguments).join(" · ") : "";
  if (args) { const s = document.createElement("small"); s.textContent = args.slice(0, 120); d.appendChild(s); }
  ajouter(d, journalOutils, 9);
  $("compte-outils").textContent = String(++appelsOutils).padStart(2, "0");
}
function outilResultat(e) {
  const d = [...journalOutils.querySelectorAll(".outil.en-cours")].reverse().find(x => x.dataset.outil === e.outil);
  if (!d) return;
  d.classList.remove("en-cours");
  d.classList.add(/a échoué|n'a pas répondu|introuvable|impossible|pas configuré|pas lancé/i.test(e.resultat) ? "echec" : "fini");
  const du = document.createElement("span"); du.className = "duree"; du.textContent = e.duree + " s"; d.querySelector("b").appendChild(du);
  const r = document.createElement("span"); r.className = "resultat"; r.textContent = e.resultat.length > 150 ? e.resultat.slice(0, 147) + "…" : e.resultat;
  d.appendChild(r);
}

// ====================================================================== événements du serveur
let sorties = 0;
function recevoir(e) {
  switch (e.type) {
    case "mot_detecte": case "ecoute": etat("ecoute"); break;
    case "micro_niveau": reacteur.micro(e.valeur); break;
    case "transcription_en_cours": etat("reflexion"); reacteur.micro(0); break;
    case "transcription": ligneMoi(e.texte); etat("reflexion"); reacteur.micro(0); break;
    case "reflexion": ligneMoi(e.question); etat("reflexion"); break;
    case "rien_entendu": note("rien entendu"); etat("repos"); reacteur.micro(0); break;
    case "jeton": surJeton(e); break;
    case "phrase": surPhrase(e); break;
    case "reponse_complete": surReponseComplete(e); if (e.source === "telegram") etat("repos"); break;
    case "parole_debut": etat("parole"); break;
    case "niveau": reacteur.niveau(e.valeur); break;
    case "parole_fin": surParoleFin(e); reacteur.niveau(0); etat("repos"); break;
    case "parole_interrompue": surInterruption(); reacteur.niveau(0); if (etatActuel === "parole") etat("repos"); break;
    case "outil_appel": outilAppel(e); break;
    case "outil_resultat": outilResultat(e); break;
    case "panneau": panneaux.ouvrir(e); break;
    case "vision":
      if (e.image) panneaux.ouvrir({ genre: "images", titre: "Webcam · ce que je vois", images: [{ url: e.image,
        legende: `${e.texte} · ${e.ecran} · ${e.enregistree ? "photo gardée dans workspace/webcam" : "image non enregistrée"} · ${e.duree} s` }] });
      else panneaux.ouvrir({ genre: "texte", titre: "Ce que je vois · " + (e.ecran || "écran"), paragraphes: [e.texte],
        source: e.duree ? `description en ${e.duree} s, sur cette machine` : "" });
      break;
    case "vision_fin": note(`écran : description en ${e.chrono.total_description || e.chrono.vision} s, cycle complet ${e.chrono.total_cycle} s`); break;
    case "image_fin": if (e.chrono && e.chrono.total_cycle) note(`image : cycle complet ${e.chrono.total_cycle} s`); break;
    case "video_etape": note("vidéo : " + e.etape); etat("reflexion"); break;
    case "verification_chiffres": note(`vérification : ${e.trouves}/${e.total} chiffres trouvés dans les faits` + (e.ecarts.length ? ` · écarts : ${e.ecarts.join(", ")}` : " · aucun écart") + (e.alertes && e.alertes.length ? ` · à revoir : ${e.alertes.join(", ")}` : "")); break;
    case "verification_phrases": note(e.inexactes.length ? `vérification des phrases : ${e.inexactes.length} inexacte(s) sur ${e.phrases}` : `vérification des phrases : ${e.phrases} exactes`); break;
    case "video_resume": note(`vidéo résumée${e.depuis_cache ? " (déjà en cache)" : ""} en ${e.duree} s` + (e.chrono && e.chrono.transcription ? ` · transcription ${e.chrono.transcription} s, résumé ${e.chrono.resume} s` : "")); break;
    case "miniatures_etape": note("miniatures : " + e.etape); etat("reflexion"); break;
    case "miniatures": note(`miniatures prêtes en ${e.duree} s · ${e.titre}`); break;
    case "video_erreur": case "miniatures_erreur": note("erreur : " + e.message); etat("erreur"); break;
    case "image": ouvrirImage(e.url + "?" + Date.now(), e.prompt, "Image générée"); break;
    case "capture": ouvrirImage(e.url + "?" + Date.now(), "capture d'écran", "Capture d'écran"); break;
    case "sortie_internet": sorties = e.total; majCompteur(); break;
    case "reglages": note(`réglages : voix ${e.voix}${e.telegram ? ", telegram prêt" : ""}`); rafraichir(); break;
    case "voix_repli": note("voix : repli local (" + e.raison + ")"); break;
    case "voix_erreur": note("erreur : " + e.message); for (const p of prises.values()) if (!p.parle) reveler(p); etat("erreur"); break;
    case "silence": voixMuette = !!e.actif; note(e.actif ? "silence jusqu'au prochain réveil" : "voix rétablie"); if (e.actif) etat("repos"); break;
    case "titre": note("je vous appellerai " + e.titre); break;
    case "commande": note("commande : " + e.commande); break;
    case "extinction": $("extinction").classList.add("visible"); break;
    case "rappel": note("rappel : " + e.texte); break;
    case "erreur": case "image_erreur": case "vision_erreur": note("erreur : " + e.message); etat("erreur"); break;
    // --- il devient humain ---
    case "fenetre_ouverte": reacteur.decompte(e.duree); $("mode").dataset.fenetre = "1"; fenetre(e.duree); break;
    case "fenetre_fermee": reacteur.finDecompte(); fenetre(0); break;
    case "interruption": note("interruption : je vous écoute"); surInterruption(); reacteur.niveau(0); etat("ecoute"); break;
    case "interruption_ignoree": note("écho de ma propre voix ignoré"); break;
    case "interruption_coupee": note("interruption coupée : trop d'écho, un casque est recommandé"); break;
    case "latence": afficherLatence(e); break;
    case "reflexe": outilAppel({ outil: "réflexe", arguments: {} }); outilResultat({ outil: "réflexe", resultat: e.reponse, duree: 0 }); break;
    case "souvenirs_utilises": surSouvenirsUtilises(e); break;
    case "souvenir_ajoute": note("mémoire : " + e.souvenir.fait + (e.doublon ? " (mis à jour)" : "")); rafraichirConstellation(); break;
    case "souvenirs_oublies": if (e.faits && e.faits.length) note("oublié : " + e.faits.join(" ; ")); rafraichirConstellation(); break;
    case "souvenirs_session": if (e.gardes.length) note(`mémoire : ${e.gardes.length} nouveau${e.gardes.length > 1 ? "x" : ""} souvenir${e.gardes.length > 1 ? "s" : ""} de la session`); break;
    case "personnalite": note("personnalité : " + e.nom); rafraichir(); break;
    case "sentinelle": note("sentinelle : " + e.texte); break;
    case "sentinelle_etat": note(e.actif ? "sentinelle activée" : "sentinelle désactivée"); break;
    case "confirmation_demandee": note("en attente de votre confirmation (oui / non)"); break;
    case "telegram_recu": note((e.vocal ? "Telegram 🎙 : " : "Telegram : ") + e.texte); break;
    case "telegram_transcrit": note("Telegram 🎙 « " + e.texte + " »"); break;
    case "telegram_refuse": surTelegramRefuse(e); break;
    case "telegram_confirmation": note("Telegram : bouton de confirmation envoyé · " + e.question); break;
    case "telegram_confirmation_reponse": note("Telegram : " + (e.choix === true ? "confirmé" : e.choix === false ? "refusé" : "sans réponse") + " · " + e.question); break;
    case "telegram_vocal_envoye": note(`Telegram : réponse vocale envoyée (${Math.round(e.octets / 1024)} Ko)`); break;
    case "outil_refuse": outilAppel(e); outilResultat({ outil: e.outil, resultat: "a échoué : " + e.raison, duree: 0 }); break;
    case "telegram_erreur": note("Telegram : " + e.message); break;
    case "connexion_ouverte": case "connexion_fermee": rafraichir(); break;
  }
}

// ---- Telegram : un inconnu écrit au bot, c'est signalé en rouge dans le journal des outils ----------------------
function surTelegramRefuse(e) {
  note(`Telegram : message refusé d'un inconnu (${e.expediteur})`);
  outilAppel({ outil: "telegram · inconnu", arguments: { expediteur: e.expediteur, chat: e.chat } });
  outilResultat({ outil: "telegram · inconnu", resultat: `a échoué : ignoré, pas votre discussion. ${e.apercu ? "« " + e.apercu + " »" : ""}`, duree: 0 });
}

// ---- conversation continue : le libellé sous le réacteur compte les secondes ----------------------------------
let minuteurFenetre = null;
function fenetre(secondes) {
  clearInterval(minuteurFenetre);
  const mode = $("mode");
  if (!secondes) { delete mode.dataset.fenetre; mode.textContent = LIBELLES[etatActuel] || etatActuel; return; }
  const fin = performance.now() + secondes * 1000;
  const maj = () => {
    const reste = Math.ceil((fin - performance.now()) / 1000);
    if (reste <= 0 || !mode.dataset.fenetre) { clearInterval(minuteurFenetre); return; }
    mode.textContent = `je vous écoute · ${reste}`;
  };
  maj(); minuteurFenetre = setInterval(maj, 200);
}

// ---- réponse éclair : le temps entre la fin de la phrase et le premier son ------------------------------------
function afficherLatence(e) {
  const s = (e.total_ms / 1000).toLocaleString("fr", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  $("latence").textContent = `${s} s`;
  const detail = [e.oreille_ms > 5 && `oreille ${e.oreille_ms} ms`, e.memoire_ms > 5 && `mémoire ${e.memoire_ms} ms`,
                  e.cerveau_ms != null && `cerveau ${e.cerveau_ms} ms`,
                  e.voix_ms != null && `voix ${e.voix_ms} ms`].filter(Boolean).join(" · ");
  $("latence-detail").textContent = detail;
  $("reponse-eclair").classList.toggle("lente", e.total_ms > 2500);
}

// ---- mémoire longue : les étoiles utilisées s'allument -------------------------------------------------------
function surSouvenirsUtilises(e) {
  outilAppel({ outil: "mémoire", arguments: {} });
  outilResultat({ outil: "mémoire", resultat: `${e.faits.length} souvenir${e.faits.length > 1 ? "s" : ""} : ${e.faits.join(" ; ")}`, duree: 0 });
  const p = panneaux.ouvertDeGenre("constellation");
  if (p && p._allumer) p._allumer(e.ids, e.faits);
}
async function rafraichirConstellation() {
  const p = panneaux.ouvertDeGenre("constellation");
  if (!p) return;
  try {
    const r = await (await fetch("/souvenirs")).json();
    panneaux.fermer(p, true);
    panneaux.ouvrir({ genre: "constellation", titre: "Ce que je sais de vous", ...r.constellation });
  } catch (_) {}
}

function connecter() {
  const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/events");
  ws.onopen = () => { $("sous-titre").textContent = "salle de briefing · en ligne"; };
  ws.onmessage = ev => recevoir(JSON.parse(ev.data));
  ws.onclose = () => { $("sous-titre").textContent = "liaison perdue, reconnexion…"; setTimeout(connecter, 2000); };
  ws.onerror = () => ws.close();
}
if (!params.get("hors_ligne")) connecter();

// ====================================================================== barre d'état et cagnotte
function majCompteur() { $("sorties").textContent = sorties; $("compteur").classList.toggle("sorti", sorties > 0); }
async function rafraichir() {
  try {
    const e = await (await fetch("/etat")).json();
    const g = e.machine && e.machine.gpu;
    if (g) {
      $("vram").textContent = `${(g.vram_utilisee_mo / 1024).toFixed(1)} / ${(g.vram_totale_mo / 1024).toFixed(0)} Go · ${g.temperature} °C`;
      $("j-vram").style.transform = `scaleX(${g.vram_utilisee_mo / g.vram_totale_mo})`;
    } else $("vram").textContent = "pas de carte NVIDIA";
    $("charges").textContent = e.charges.length ? e.charges.join(", ") : "rien en mémoire";
    let cerveau = e.cerveau.distant ? "distant · " + e.cerveau.modele : "local · " + e.cerveau.modele;
    if (e.solde) cerveau += e.solde.erreur ? " · passerelle injoignable" : ` · ${e.solde.credit_minutes} min (${e.solde.credit_euros} €)`;
    $("cerveau").textContent = cerveau;
    $("cerveau-mode").classList.toggle("distant", e.cerveau.distant);
    $("voix").textContent = e.voix.moteur === "elevenlabs" ? (e.voix.elevenlabs ? "ElevenLabs (internet)" : "ElevenLabs absent → Kokoro") : "Kokoro · 100 % local";
    voixMuette = !!e.silence;
    if (e.silence) $("voix").textContent += " · silence";
    if (e.service_cloud && e.service_cloud.actif) {
      const s = e.service_cloud, b = s.bilan;
      $("charges").textContent += s.tunnel ? " · sert le cloud" : s.passerelle ? " · cloud sans tunnel" : " · cloud en panne";
      if (b) $("charges").textContent += ` · ${b.clients} client${b.clients > 1 ? "s" : ""}, ${Math.round(b.secondes / 60)} min, ${b.euros} €`;
    }
    sorties = e.sorties_internet.total; majCompteur();
    const connexions = (e.sorties_internet.connexions || []);
    $("connexions").textContent = connexions.length ? "+ écoute " + connexions.join(", ") : "";
    if (e.personnalite) $("personnalite").textContent = e.personnalite;
    if (e.souvenirs !== undefined) $("nb-souvenirs").textContent = e.souvenirs;
    if (e.latence && !$("latence").textContent.trim().match(/\d/)) afficherLatence(e.latence);
    for (const b of ["cerveau", "whisper", "micro", "voix"]) $("v-" + b).classList.toggle("ok", !!(e.pret && e.pret[b]));
  } catch (_) {}
}
rafraichir(); setInterval(rafraichir, 2000);

async function cagnotte() {
  try {
    const e = await (await fetch("/etat")).json();
    if (!e.cagnotte_url) return;
    // l'en-tête ngrok seulement vers ngrok : envoyé à GitHub Pages, il déclenche un contrôle CORS refusé
    const entetes = e.cagnotte_url.includes("ngrok") ? { "ngrok-skip-browser-warning": "1" } : {};
    const c = await (await fetch(e.cagnotte_url, { headers: entetes })).json();
    const b = $("soutenir");
    b.hidden = false;
    b.textContent = `Soutenir · ${c.total.toLocaleString("fr", { style: "currency", currency: "EUR" })}` + (c.prochain ? ` / ${c.prochain.montant} €` : "");
    b.title = c.prochain ? `Prochain objectif, ${c.prochain.montant} € : ${c.prochain.titre}` : "Tous les objectifs sont atteints, merci";
    b.onclick = () => window.open(c.lien || e.cagnotte_url.replace("/cagnotte.json", "/"), "_blank");
  } catch (_) {}
}
if (!params.get("hors_ligne")) { cagnotte(); setInterval(cagnotte, 600000); }

// ====================================================================== réglages (un grand panneau)
function ouvrirReglages() {
  panneaux.ouvrir({ genre: "formulaire", titre: "Réglages", construire: async corps => {
    const r = await (await fetch("/reglages")).json();
    const f = document.createElement("form"); f.className = "reglages"; f.autocomplete = "off";
    const creer = (balise, classe, texte) => { const x = document.createElement(balise); if (classe) x.className = classe; if (texte) x.textContent = texte; return x; };
    const champs = {};
    const bloc = titre => f.appendChild(creer("h4", "", titre));
    const libelleCle = c => c.definie ? `enregistrée ${c.apercu} (laisser vide pour garder, « - » pour effacer)` : "à coller ici";
    const cle = nom => {
      const c = r.cles[nom], d = creer("div");
      d.appendChild(creer("label", "", c.libelle));
      const ligne = creer("div", "ligne"), i = creer("input"); i.type = "password"; i.placeholder = libelleCle(c); champs[nom] = i;
      ligne.append(i, creer("span", "etat" + (c.definie ? " ok" : ""), c.definie ? "définie" : "absente"));
      d.append(ligne, creer("small", "", c.aide)); f.appendChild(d);
    };
    const message = creer("div", "message");
    const dire = (texte, erreur) => { message.textContent = texte; message.classList.toggle("erreur", !!erreur); };
    const tester = async quoi => { dire("test en cours…"); const t = await (await fetch(`/reglages/tester/${quoi}`, { method: "POST" })).json(); dire(t.message, !t.ok); };
    const choix = (options, valeur) => { const s = creer("select"); options.forEach(([v, t]) => { const o = creer("option", "", t); o.value = v; s.appendChild(o); }); s.value = valeur; return s; };
    const bouton = (texte, action) => { const b = creer("button", "", texte); b.type = "button"; b.onclick = action; return b; };
    const caseACocher = (libelle, coche, aide) => {
      const d = creer("div", "case"), l = creer("label"), c = creer("input");
      c.type = "checkbox"; c.checked = !!coche; l.append(c, document.createTextNode(" " + libelle)); d.appendChild(l);
      if (aide) d.appendChild(creer("small", "", aide));
      f.appendChild(d); return c;
    };
    const nombre = (libelle, valeur, min, max, pas, aide) => {
      const d = creer("div"); d.appendChild(creer("label", "", libelle));
      const i = creer("input"); i.type = "number"; i.min = min; i.max = max; i.step = pas; i.value = valeur;
      const ligne = creer("div", "ligne"); ligne.appendChild(i); d.appendChild(ligne);
      if (aide) d.appendChild(creer("small", "", aide));
      f.appendChild(d); return i;
    };

    bloc("personnalité");
    const perso = choix(r.personnalite.choix.map(p => [p.nom, `${p.libelle} · ${p.description}`]), r.personnalite.actuelle);
    const dp = creer("div"); dp.appendChild(creer("label", "", "Ton de Jarvis"));
    const lp = creer("div", "ligne"); lp.appendChild(perso); dp.append(lp,
      creer("small", "", "Même mémoire, mêmes outils, seul le ton change. À la voix : « Jarvis, passe en mode coach »."));
    f.appendChild(dp);

    bloc("conversation");
    const cContinue = caseACocher("Conversation continue", r.conversation.continue,
      "Après chaque réponse, Jarvis écoute encore quelques secondes sans qu'il faille redire « Jarvis ». Un anneau décompte autour du réacteur.");
    const cSecondes = nombre("Durée d'écoute après une réponse (secondes)", r.conversation.secondes, 2, 30, 1);
    const cInterruption = caseACocher("Interruption", r.conversation.interruption,
      "Parlez pendant que Jarvis parle : il se tait et traite votre nouvelle phrase. Casque recommandé : avec des haut-parleurs, "
      + "Jarvis s'entend lui-même ; il reconnaît cet écho et coupe l'interruption s'il se répète.");
    const dsens = creer("div"); dsens.appendChild(creer("label", "", "Sensibilité de l'interruption"));
    const sens = choix([["faible", "faible · il faut parler fort et longtemps"], ["normale", "normale"], ["forte", "forte · au moindre mot (casque conseillé)"]],
      r.conversation.sensibilite);
    const ls = creer("div", "ligne"); ls.appendChild(sens); dsens.appendChild(ls); f.appendChild(dsens);
    const cAnglais = caseACocher("Répondre en anglais quand je parle anglais", r.conversation.anglais,
      "La langue est reconnue à chaque phrase. En anglais, Jarvis répond en anglais avec une voix anglaise.");
    const dvEn = creer("div"); dvEn.appendChild(creer("label", "", "Voix anglaise (Kokoro, locale)"));
    const voixEn = choix(r.voix.voix_anglaises.map(v => [v.id, v.libelle]), r.voix.kokoro_voix_en);
    const lvEn = creer("div", "ligne"); lvEn.appendChild(voixEn); dvEn.appendChild(lvEn); f.appendChild(dvEn);

    bloc("mémoire");
    const cMemoire = caseACocher("Mémoire longue", r.memoire.actif,
      "Jarvis retient des faits sur vous d'une session à l'autre (« retiens que… », « oublie que… », « qu'est-ce que tu sais de moi »). "
      + "Tout reste dans le dossier memoire, sur cette machine.");
    const am = creer("div", "actions"); am.appendChild(bouton("voir la constellation", () => fetch("/souvenirs/constellation", { method: "POST" })));
    f.appendChild(am);

    bloc("sentinelle");
    const cSentinelle = caseACocher("Surveillance en tâche de fond", r.sentinelle.actif,
      "Jarvis parle de lui-même si la carte graphique chauffe, si un disque est presque plein ou si un rappel approche, au plus une fois toutes les 10 minutes par sujet.");
    const sTemp = nombre("Alerte de température de la carte (°C)", r.sentinelle.temperature_max, 60, 100, 1);
    const sDisque = nombre("Alerte d'espace disque sous (Go)", r.sentinelle.disque_min_go, 1, 500, 1);

    bloc("voix");
    const moteur = choix([["local", "Kokoro, locale et gratuite"], ["elevenlabs", "ElevenLabs, en ligne (clé requise)"]], r.voix.moteur);
    const dv = creer("div"); dv.appendChild(creer("label", "", "Moteur de voix"));
    const lv = creer("div", "ligne"); lv.append(moteur, bouton("tester la clé", () => tester("elevenlabs"))); dv.appendChild(lv); f.appendChild(dv);
    cle("ELEVENLABS_API_KEY");
    const voixSel = choix([[r.voix.elevenlabs_voix, r.voix.elevenlabs_voix || "aucune voix choisie"]], r.voix.elevenlabs_voix);
    const dx = creer("div"); dx.appendChild(creer("label", "", "Voix ElevenLabs"));
    const lx = creer("div", "ligne");
    lx.append(voixSel, bouton("lister mes voix", async () => {
      dire("voix en cours de chargement…");
      const j = await (await fetch("/reglages/voix_elevenlabs")).json();
      if (!j.voix.length) return dire(j.erreur ? `ElevenLabs ne répond pas (${j.erreur})` : "Aucune voix : enregistrez d'abord la clé ElevenLabs.", true);
      voixSel.innerHTML = "";
      j.voix.forEach(v => { const o = creer("option", "", v.nom + (v.detail ? ` · ${v.detail}` : "")); o.value = v.id; voixSel.appendChild(o); });
      if ([...voixSel.options].some(o => o.value === r.voix.elevenlabs_voix)) voixSel.value = r.voix.elevenlabs_voix;
      dire(`${j.voix.length} voix disponibles, choisissez puis enregistrez.`);
    }));
    dx.append(lx, creer("small", "", "Chaque phrase ElevenLabs est une sortie Internet (compteur en bas). Si ElevenLabs échoue, Jarvis repasse sur Kokoro."));
    f.appendChild(dx);

    bloc("telegram");
    const messageT = creer("div", "message");
    const direT = (texte, erreur) => { messageT.textContent = texte; messageT.classList.toggle("erreur", !!erreur); };
    const etape = (n, texte) => { const d = creer("div", "etape"); d.append(creer("b", "", String(n)), creer("span", "", texte)); f.appendChild(d); return d; };
    const e1 = etape(1, "Dans Telegram, ouvrez @BotFather, envoyez /newbot, donnez un nom puis un identifiant qui finit par « bot ». "
      + "BotFather répond avec un jeton du genre 123456789:AAH…");
    e1.appendChild(bouton("ouvrir @BotFather", () => window.open("https://t.me/BotFather", "_blank")));
    etape(2, "Collez le jeton ici, puis vérifiez-le.");
    cle("TELEGRAM_TOKEN");
    const aj = creer("div", "actions");
    aj.appendChild(bouton("vérifier le jeton", async () => {
      direT("vérification…");
      const j = await (await fetch("/reglages/telegram/verifier_jeton", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jeton: champs.TELEGRAM_TOKEN.value.trim() }) })).json();
      direT(j.message, !j.ok);
      if (j.ok && j.lien && !aj.querySelector(".lien-bot")) { const b = bouton(`ouvrir @${j.bot}`, () => window.open(j.lien, "_blank")); b.classList.add("lien-bot"); aj.appendChild(b); }
    }));
    f.appendChild(aj);
    etape(3, "Ouvrez votre bot, appuyez sur Démarrer et envoyez-lui « bonjour ». Jarvis lit ce message pour trouver votre identifiant.");
    const ai = creer("div", "actions");
    ai.appendChild(bouton("trouver mon identifiant", async () => {
      direT("recherche de votre message…");
      const j = await (await fetch("/reglages/telegram/trouver_identifiant", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jeton: champs.TELEGRAM_TOKEN.value.trim() }) })).json();
      direT(j.message, !j.ok);
      if (j.ok) { champs.TELEGRAM_CHAT_ID.value = j.identifiant; champs.TELEGRAM_CHAT_ID.type = "text"; }
    }));
    f.appendChild(ai);
    f.appendChild(messageT);
    etape(4, "Enregistrez en bas du panneau, puis envoyez un message de test.");
    cle("TELEGRAM_CHAT_ID");
    const at = creer("div", "actions"); at.appendChild(bouton("envoyer un message de test", () => tester("telegram"))); f.appendChild(at);
    const cTelegram = caseACocher("Commandes depuis le téléphone", r.telegram.commandes,
      "Écrivez ou envoyez un vocal à votre bot : /etat, /capture, /image, /notes, /rappel, /dire, /silence, ou une question libre. "
      + "Seul l'identifiant ci-dessus est obéi ; tout autre expéditeur est ignoré et signalé ici. "
      + "Une action sur le PC (fenêtres, rangement, frappe…) attend votre bouton « Oui » dans Telegram.");
    const cVocal = caseACocher("Réponse aussi en vocal", r.telegram.reponse_vocale,
      "Jarvis répond en texte puis en message vocal, avec sa voix locale.");

    bloc("youtube");
    const messageY = creer("div", "message");
    const direY = (texte, erreur) => { messageY.textContent = texte; messageY.classList.toggle("erreur", !!erreur); };
    const ey1 = etape(1, "Ouvrez Google Cloud et créez un projet (le nom est libre).");
    ey1.appendChild(bouton("ouvrir Google Cloud", () => window.open("https://console.cloud.google.com/projectcreate", "_blank")));
    const ey2 = etape(2, "Dans la bibliothèque d'API, activez « YouTube Data API v3 ».");
    ey2.appendChild(bouton("ouvrir l'API", () => window.open("https://console.cloud.google.com/apis/library/youtube.googleapis.com", "_blank")));
    const ey3 = etape(3, "Identifiants › Créer des identifiants › Clé API. Limitez la clé à YouTube Data API v3, copiez-la.");
    ey3.appendChild(bouton("ouvrir Identifiants", () => window.open("https://console.cloud.google.com/apis/credentials", "_blank")));
    etape(4, "Collez la clé, enregistrez, puis testez. Sans clé, Jarvis lit les pages publiques (plus lent, sans quota).");
    cle("YOUTUBE_API_KEY");
    const ay = creer("div", "actions"), quotaY = creer("span", "etat");
    const majQuota = async () => { try { const j = await (await fetch("/reglages/youtube")).json();
      quotaY.textContent = `quota : ${j.quota.utilise} / ${j.quota.limite} unités aujourd'hui · source ${j.source === "api" ? "API" : "pages publiques"}`;
      oauthEtat.textContent = j.oauth.connecte ? `compte connecté : ${j.oauth.compte || "oui"}` : j.oauth.client ? "identifiant importé, compte non connecté" : "pas d'OAuth (statistiques publiques)";
      if (j.oauth.message) direY(j.oauth.message); } catch (_) {} };
    ay.append(bouton("tester la clé", async () => { direY("test en cours…"); const t = await (await fetch("/reglages/tester/youtube", { method: "POST" })).json(); direY(t.message, !t.ok); majQuota(); }), quotaY);
    f.appendChild(ay);
    const dch = creer("div"); dch.appendChild(creer("label", "", "Ma chaîne (son @ ou son nom)"));
    const maChaine = creer("input"); maChaine.value = r.youtube.ma_chaine; maChaine.placeholder = "@machaine";
    const lch = creer("div", "ligne"); lch.appendChild(maChaine); dch.append(lch, creer("small", "", "Pour le briefing et « analyse ma chaîne »."));
    f.appendChild(dch);
    const dco = creer("div"); dco.appendChild(creer("label", "", "Concurrents (jusqu'à 5, séparés par des virgules)"));
    const concurrents = creer("input"); concurrents.value = r.youtube.concurrents; concurrents.placeholder = "@chaine1, @chaine2";
    const lco = creer("div", "ligne"); lco.appendChild(concurrents); dco.append(lco, creer("small", "", "Le briefing signale une de leurs vidéos au-dessus de 3 fois leur médiane cette semaine."));
    f.appendChild(dco);
    const avance = creer("details", "avance"); avance.appendChild(creer("summary", "", "avancé : statistiques privées de ma chaîne (OAuth)"));
    avance.appendChild(creer("small", "", "Rétention et sources de trafic. Dans Google Cloud : écran de consentement OAuth (type Externe, ajoutez-vous "
      + "comme utilisateur test), puis Identifiants › ID client OAuth › « Application de bureau » › télécharger le JSON. Accès en lecture seule. "
      + "Le fichier reste sur cette machine (.youtube_oauth.json)."));
    const oauthEtat = creer("span", "etat");
    const fichierOauth = creer("input"); fichierOauth.type = "file"; fichierOauth.accept = ".json,application/json";
    const ao = creer("div", "actions");
    ao.append(fichierOauth, bouton("importer le fichier", async () => {
      if (!fichierOauth.files.length) return direY("Choisissez d'abord le fichier JSON téléchargé.", true);
      const donnees = new FormData(); donnees.append("fichier", fichierOauth.files[0]);
      const j = await (await fetch("/reglages/youtube/oauth_client", { method: "POST", body: donnees })).json(); direY(j.message, !j.ok); majQuota(); }),
      bouton("connecter mon compte", async () => { const j = await (await fetch("/reglages/youtube/connecter", { method: "POST" })).json(); direY(j.message, !j.ok);
        const suivi = setInterval(async () => { await majQuota(); if (!(await (await fetch("/reglages/youtube")).json()).oauth.en_cours) clearInterval(suivi); }, 2000); }),
      bouton("déconnecter", async () => { const j = await (await fetch("/reglages/youtube/deconnecter", { method: "POST" })).json(); direY(j.message); majQuota(); }),
      oauthEtat);
    avance.appendChild(ao); f.appendChild(avance); f.appendChild(messageY);
    majQuota();

    bloc("jarvis cloud");
    const mode = choix([["local", "local, sur cette machine (Ollama)"], ["cloud", "Jarvis Cloud, sur la machine de l'auteur (jeton requis)"]], r.cerveau.mode);
    const dc = creer("div"); dc.appendChild(creer("label", "", "Cerveau"));
    const lc = creer("div", "ligne"); lc.append(mode, bouton("vérifier le crédit", () => tester("cloud")));
    dc.append(lc, creer("small", "", "Changer de cerveau demande de relancer Jarvis (lancer.bat).")); f.appendChild(dc);
    cle("CLOUD_TOKEN");

    const actions = creer("div", "actions"), ok = creer("button", "", "enregistrer"); ok.type = "submit";
    actions.append(ok, message); f.appendChild(actions);
    f.onsubmit = async ev => {
      ev.preventDefault();
      const cles = {}; for (const [k, i] of Object.entries(champs)) if (i.value.trim()) cles[k] = i.value.trim();
      const res = await fetch("/reglages", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cles, voix: { moteur: moteur.value, elevenlabs_voix: voixSel.value, kokoro_voix_en: voixEn.value },
          cerveau: { mode: mode.value }, personnalite: { actuelle: perso.value },
          conversation: { continue: cContinue.checked, secondes: Number(cSecondes.value), interruption: cInterruption.checked,
                          sensibilite: sens.value, anglais: cAnglais.checked },
          memoire: { actif: cMemoire.checked }, youtube: { ma_chaine: maChaine.value, concurrents: concurrents.value }, telegram: { commandes: cTelegram.checked, reponse_vocale: cVocal.checked },
          sentinelle: { actif: cSentinelle.checked, temperature_max: Number(sTemp.value), disque_min_go: Number(sDisque.value) } }) });
      if (!res.ok) return dire("enregistrement refusé", true);
      const j = await res.json();
      for (const [k, i] of Object.entries(champs)) {
        const c = j.cles[k]; i.value = ""; i.placeholder = libelleCle(c);
        const e = i.nextElementSibling; e.className = "etat" + (c.definie ? " ok" : ""); e.textContent = c.definie ? "définie" : "absente";
      }
      dire(j.redemarrer ? "Enregistré. Relancez Jarvis pour changer de cerveau." : "Enregistré et appliqué.");
      rafraichir();
    };
    corps.appendChild(f);
  } });
}
$("reglages").onclick = ouvrirReglages;

// ====================================================================== saisie, micro du navigateur, raccourcis
let occupe = false, enregistreur = null, morceaux = [], flux = null, animMicro = null;
async function envoyerTexte(texte) {
  if (occupe || !texte.trim()) return;
  occupe = true;
  try {
    const rep = await (await fetch("/parler", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ texte }) })).json();
    if (rep.erreur) { note("erreur : " + rep.erreur); etat("erreur"); }
  } catch (e) { note("erreur : " + e.message); etat("erreur"); }
  occupe = false;
}
$("saisie").onsubmit = e => { e.preventDefault(); const t = $("texte").value; $("texte").value = ""; envoyerTexte(t); };
// Entrée envoie, même quand la soumission implicite du formulaire ne se déclenche pas (touches simulées, certains navigateurs)
$("texte").addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); $("saisie").requestSubmit(); } });
$("oublier").onclick = () => fetch("/oublier", { method: "POST" }).then(() => { transcription.innerHTML = ""; prises.clear(); note("conversation effacée"); });
$("memoire").onclick = () => {
  const p = panneaux.ouvertDeGenre("constellation");
  if (p) panneaux.fermer(p); else fetch("/souvenirs/constellation", { method: "POST" });
};
$("taire").onclick = () => fetch("/taire", { method: "POST" });

function basculerPleinEcran() { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen().catch(() => {}); }

async function demarrerEcoute() {
  if (occupe || enregistreur) return;
  fetch("/taire", { method: "POST" });
  try { flux = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }); }
  catch (e) { note("micro du navigateur refusé : " + e.message); return; }
  // un seul micro à la fois (sinon chaque phrase est traitée deux fois), et seulement une fois celui du navigateur
  // ouvert : refusé, il laissait le micro du PC en pause jusqu'au redémarrage (audit du 19/09)
  fetch("/oreilles/pause", { method: "POST" });
  const actx = new AudioContext(), analyseur = actx.createAnalyser(); analyseur.fftSize = 256;
  actx.createMediaStreamSource(flux).connect(analyseur);
  const donnees = new Uint8Array(analyseur.frequencyBinCount);
  (function boucle() {
    animMicro = requestAnimationFrame(boucle); analyseur.getByteTimeDomainData(donnees);
    let s = 0; for (const v of donnees) s += (v - 128) ** 2; reacteur.micro(Math.sqrt(s / donnees.length) / 40);
  })();
  morceaux = [];
  enregistreur = new MediaRecorder(flux, { mimeType: "audio/webm;codecs=opus" });
  enregistreur.ondataavailable = e => morceaux.push(e.data);
  enregistreur.onstop = envoyerAudio;
  enregistreur.start();
  etat("ecoute");
}
function arreterEcoute() {
  if (!enregistreur) return;
  enregistreur.stop(); flux.getTracks().forEach(t => t.stop()); enregistreur = null;
  cancelAnimationFrame(animMicro); reacteur.micro(0);
}
async function envoyerAudio() {
  const blob = new Blob(morceaux, { type: "audio/webm" });
  setTimeout(() => fetch("/oreilles/reprise", { method: "POST" }), 800);   // la fin de phrase ne repart pas par le micro du PC
  if (blob.size < 2000) { etat("repos"); return; }
  occupe = true; etat("reflexion");
  const corps = new FormData(); corps.append("audio", blob, "voix.webm");
  try { const rep = await (await fetch("/ecouter", { method: "POST", body: corps })).json(); if (!rep.transcription) etat("repos"); }
  catch (e) { note("erreur : " + e.message); etat("erreur"); }
  occupe = false;
}
// maintenir le clic sur le réacteur pour parler
$("scene").addEventListener("pointerdown", e => { if (reacteur.estSur(e.clientX, e.clientY)) { e.preventDefault(); demarrerEcoute(); } });
addEventListener("pointerup", arreterEcoute);

function basculerDiscret(actif) {
  document.body.classList.toggle("discret", actif);
  reacteur.discret(actif);
  recentrer(actif ? 0 : panneaux.nombre);
  try { localStorage.setItem("jarvis.discret", actif ? "1" : ""); } catch (_) {}
}
document.addEventListener("keydown", e => {
  const cible = document.activeElement;
  const saisie = cible && (cible.tagName === "INPUT" || cible.tagName === "SELECT" || cible.tagName === "TEXTAREA");
  if (e.code === "Escape") { fetch("/taire", { method: "POST" }); voile.classList.remove("visible"); panneaux.fermerTout(); return; }
  if (saisie || e.ctrlKey || e.altKey || e.metaKey) return;
  if (e.code === "Space" && !e.repeat) { e.preventDefault(); demarrerEcoute(); }
  else if (e.code === "KeyF") basculerPleinEcran();
  else if (e.code === "KeyP") { if (panneaux.nombre) panneaux.fermerTout(); else panneaux.rouvrir(); }
  else if (e.code === "KeyM" || e.key === "m" || e.key === "M") basculerDiscret(!document.body.classList.contains("discret"));
});
document.addEventListener("keyup", e => { if (e.code === "Space") arreterEcoute(); });

try { if (localStorage.getItem("jarvis.discret")) basculerDiscret(true); } catch (_) {}

if (params.get("plein")) {
  const premier = () => { if (!document.fullscreenElement) document.documentElement.requestFullscreen().catch(() => {});
    document.removeEventListener("pointerdown", premier); document.removeEventListener("keydown", premier); };
  document.addEventListener("pointerdown", premier); document.addEventListener("keydown", premier);
}

// ====================================================================== captures et mesures (Edge headless, CDP)
// ?demo=1&etat=parole&panneaux=graphique,liste&discret=1&ips=1&boot=1&extinction=1&hors_ligne=1
const DEMO = {
  graphique: { genre: "graphique", titre: "État de la machine", legende_courbe: "charge de la carte graphique, dernières minutes",
    jauges: [{ nom: "Mémoire vidéo", valeur: 12.6, max: 16, unite: "Go" }, { nom: "Charge carte graphique", valeur: 38, max: 100, unite: "%" },
      { nom: "Température carte", valeur: 61, max: 100, unite: "°C" }, { nom: "Processeur", valeur: 14, max: 100, unite: "%" },
      { nom: "Mémoire vive", valeur: 11.2, max: 15.8, unite: "Go" }, { nom: "Disque C", valeur: 418, max: 465, unite: "Go", alerte: true }],
    courbe: [4, 6, 5, 9, 22, 61, 88, 93, 90, 72, 41, 18, 12, 30, 76, 95, 97, 94, 63, 28, 15, 11, 9, 38] },
  liste: { genre: "liste", titre: "Notes", elements: [
    { titre: "Acheter du filament PLA noir pour l'imprimante", meta: "16/09 18:42" },
    { titre: "Rappeler le garage pour le contrôle technique", meta: "16/09 09:15" },
    { titre: "Idée de vidéo : Jarvis qui monte une vidéo tout seul", meta: "15/09 23:58" },
    { titre: "Tester la voix ElevenLabs sur la démo", meta: "15/09 21:03" },
    { titre: "Sauvegarder le disque F avant la mise à jour", meta: "14/09 17:20" }] },
  images: { genre: "images", titre: "Image générée", images: [{ url: "/workspace/images/image_20260915_015256.png", legende: "un phare breton sous l'orage, peinture à l'huile" }] },
  galerie: { genre: "images", titre: "Images de la session", images: [
    { url: "/workspace/images/image_20260915_015256.png", legende: "phare sous l'orage" }, { url: "/workspace/images/image_20260915_014712.png", legende: "essai 2" },
    { url: "/workspace/images/image_20260915_010249.png", legende: "essai 1" }] },
  frise: { genre: "frise", titre: "Rappels à venir", evenements: [0, 1, 2, 3, 4].map(i => ({ quand: Date.now() / 1000 + [20, 75, 180, 400, 1500][i] * 60,
    titre: ["Sortir le pain du four", "Appel avec l'éditeur", "Lancer le rendu de la vidéo", "Arroser les plantes", "Réunion de chaîne"][i] })) },
  texte: { genre: "texte", titre: "Ce que je vois · écran principal", source: "description en 4,2 s, sur cette machine",
    paragraphes: ["Vous montez une vidéo dans Filmora : la piste principale montre le HUD de Jarvis, avec une piste de musique en dessous.",
      "Le curseur est arrêté à 12 minutes 43, sur un plan où l'on voit la météo s'afficher."] },
  recherche: { genre: "recherche", titre: "Recherche : phares bretons", externe: "https://duckduckgo.com/?q=phares+bretons", resultats: [
    { titre: "Quels sont tous les phares bretons ?", domaine: "portdattache.bzh", url: "https://www.portdattache.bzh/", extrait: "Avec ce guide complet des phares bretons, devenez incollable sur ces géants des mers." },
    { titre: "Liste des phares de Bretagne — Wikipédia", domaine: "fr.wikipedia.org", url: "https://fr.wikipedia.org/wiki/Liste_des_phares_de_Bretagne", extrait: "Liste des phares situés sur les côtes bretonnes." },
    { titre: "Les 10 plus beaux phares de Bretagne", domaine: "tourismebretagne.com", url: "https://www.tourismebretagne.com/", extrait: "Ar-Men, la Vieille, Eckmühl, le Créac'h, les sentinelles de la mer d'Iroise." }] },
};
function demoConversation() {
  ligneMoi("Jarvis, dans quel état est la machine ?");
  outilAppel({ outil: "etat_machine", arguments: {} });
  outilResultat({ outil: "etat_machine", duree: 0.4, resultat: "mémoire vidéo 12.6 gigaoctets utilisés sur 16, carte graphique à 61 degrés et 38 % de charge" });
  const p = prise(1); p.dit = "Il vous reste 3,4 gigaoctets de mémoire vidéo, monsieur, et la carte est à 61 degrés."; p.parle = true; afficher(p, p.dit); p.el.classList.remove("en-cours");
  ligneMoi("Rappelle-moi de sortir le pain dans vingt minutes.");
  outilAppel({ outil: "rappel", arguments: { quand: "dans 20 minutes", texte: "sortir le pain" } });
  outilResultat({ outil: "rappel", duree: 0.1, resultat: "Rappel programmé aujourd'hui à 20 h 42 (dans 20 minutes) : sortir le pain." });
  outilAppel({ outil: "generer_image", arguments: { description: "un phare breton sous l'orage" } });
}
if (params.get("demo")) {
  demoConversation();
  for (const nom of (params.get("panneaux") || "").split(",").filter(Boolean)) {
    if (nom === "reglages") ouvrirReglages(); else if (DEMO[nom]) panneaux.ouvrir(DEMO[nom]);
  }
}
const force = params.get("etat");
if (force) {
  etat(force);
  if (force === "parole") setInterval(() => reacteur.niveau(0.3 + 0.65 * Math.abs(Math.sin(performance.now() / 170))), 50);
  if (force === "ecoute") setInterval(() => reacteur.micro(0.3 + 0.65 * Math.abs(Math.sin(performance.now() / 210))), 50);
  if (force === "erreur") { reacteur.erreurLongue(); etat = () => {}; }
  if (force === "reflexion" && params.get("demo")) ligneMoi("Jarvis, qu'est-ce que tu sais des phares bretons ?");
}
if (params.get("discret")) basculerDiscret(true);
if (params.get("extinction")) $("extinction").classList.add("visible");
if (params.get("ips")) {
  document.body.classList.add("avec-ips");
  setInterval(() => { const s = reacteur.stats(120); $("ips").textContent = `${s.ips} i/s · p95 ${s.p95_ms} ms · ${s.taille ? s.taille.join("×") : ""}`; }, 500);
}

// rejoue un enregistrement d'événements réels au rythme d'origine (vérification sans micro ni haut-parleur)
function rejouer(evenements) {
  const t0 = evenements[0].t, debut = performance.now();
  evenements.forEach(e => setTimeout(() => recevoir(e), Math.max(0, (e.t - t0) * 1000 - (performance.now() - debut))));
  return (evenements[evenements.length - 1].t - t0);
}
window.__jarvis = { reacteur, panneaux, recevoir, rejouer, etat, basculerDiscret, ouvrirReglages, DEMO };
