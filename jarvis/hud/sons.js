// Les sons d'interface, synthétisés dans le navigateur (Web Audio) : aucun fichier, rien de téléchargé. Chaque armure
// a son timbre (themes.js : forme d'onde, note, filtre, durée). Touche S pour les couper, mémorisé dans le navigateur.
// Le contexte audio ne naît qu'au premier geste (règle des navigateurs) ; avant, les sons sont simplement ignorés.
import { THEMES, THEME_DEFAUT } from "./themes.js";

const VOLUME = 0.12;

export function creerSons() {
  let ctx = null, sortie = null;
  let actif = true;
  try { actif = localStorage.getItem("jarvis.sons") !== "0"; } catch (_) {}

  function contexte() {
    if (ctx) return ctx;
    try {
      ctx = new AudioContext();
      sortie = ctx.createGain(); sortie.gain.value = VOLUME; sortie.connect(ctx.destination);
    } catch (_) { ctx = null; }
    return ctx;
  }
  const premier = () => { const c = contexte(); if (c && c.state === "suspended") c.resume(); };
  addEventListener("pointerdown", premier); addEventListener("keydown", premier);

  // une note : attaque rapide, décroissance, un filtre passe-bas qui donne le caractère de l'armure
  function note(t, frequence, duree, son, { vers = null, force = 1 } = {}) {
    const osc = ctx.createOscillator(), filtre = ctx.createBiquadFilter(), g = ctx.createGain();
    osc.type = son.forme;
    osc.frequency.setValueAtTime(frequence, t);
    if (vers) osc.frequency.exponentialRampToValueAtTime(vers, t + duree);
    filtre.type = "lowpass"; filtre.frequency.value = son.filtre; filtre.Q.value = 4;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.9 * force, t + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, t + duree);
    osc.connect(filtre).connect(g).connect(sortie);
    osc.start(t); osc.stop(t + duree + 0.05);
  }

  const MOTIFS = {
    // réveil : deux notes qui montent
    reveil: (t, s) => { note(t, s.note, s.duree, s); note(t + s.duree * 0.9, s.note * 1.5, s.duree * 1.2, s); },
    // un panneau s'ouvre : un bip court
    panneau: (t, s) => note(t, s.note * 1.25, s.duree * 0.8, s, { force: 0.7 }),
    // fin de réponse : une note qui retombe
    fin: (t, s) => note(t, s.note, s.duree * 2, s, { vers: s.note * 0.75, force: 0.6 }),
    // erreur : deux notes graves
    erreur: (t, s) => { note(t, s.note * 0.5, 0.12, s); note(t + 0.14, s.note * 0.42, 0.18, s); },
    // la recharge d'armure : descente pendant l'extinction (0,45 s), puis montée en surcharge avec l'ancienne armure
    // qui s'éteint et la nouvelle qui s'allume
    extinction: (t, s) => note(t, s.note, 0.45, s, { vers: Math.max(40, s.note / 6), force: 0.8 }),
    allumage: (t, s) => {
      note(t, 55, 0.35, { ...s, forme: "sine", filtre: 400 }, { force: 1 });                   // le choc
      note(t, Math.max(60, s.note / 4), 1.1, s, { vers: s.note * 1.5, force: 0.7 });          // la montée en charge
      note(t + 0.5, s.note * 1.5, 0.5, s, { force: 0.5 });                                      // le « prêt »
    },
  };

  return {
    get actif() { return actif; },
    basculer(v = !actif) {
      actif = v;
      try { localStorage.setItem("jarvis.sons", actif ? "1" : "0"); } catch (_) {}
      return actif;
    },
    jouer(motif, theme = THEME_DEFAUT) {
      if (!actif || !MOTIFS[motif]) return false;
      const c = contexte();
      if (!c || c.state !== "running") return false;
      MOTIFS[motif](c.currentTime + 0.01, (THEMES[theme] || THEMES[THEME_DEFAUT]).son);
      return true;
    },
  };
}
