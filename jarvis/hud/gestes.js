// La lecture des gestes (v3, consigne 5) : à partir des 21 points de chaque main donnés par MediaPipe, dire ce que
// la personne fait. Aucun accès caméra ici, aucune dépendance : rien que du calcul sur des points, ce qui permet de
// tester tous les gestes en rejouant des suites de points (jarvis/tests/gestes.py).
//
// Points MediaPipe utilisés : 0 poignet, 4 pouce, 8 index, 12 majeur, 16 annulaire, 20 auriculaire,
// 5/9/13/17 base des doigts. Coordonnées normalisées (0 à 1), origine en haut à gauche de l'image.

export const SEUILS = {
  pince: 0.42,            // distance pouce-index rapportée à la taille de la main : en dessous, c'est une pince
  relache: 0.55,          // hystérésis : il faut rouvrir franchement pour lâcher
  balayage_vitesse: 1.1,  // largeurs d'image par seconde
  balayage_course: 0.22,  // et au moins ce déplacement, pour ne pas confondre avec un mouvement ordinaire
  main_ouverte_s: 3,      // main ouverte et immobile : réveil
  immobile: 0.35,         // vitesse au-dessous de laquelle la main est considérée immobile
  rotation_min: 0.06,     // radians : en dessous, c'est du tremblement
  zoom_min: 0.015,        // variation d'écart entre les deux mains, en dessous c'est du tremblement
};

const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

/** Les mesures d'une main : où elle est, si elle pince, si elle est ouverte, comment le poignet est tourné. */
export function mesurer(points) {
  const paume = distance(points[0], points[9]) || 1e-6;        // la taille apparente de la main (échelle)
  const pince = distance(points[4], points[8]) / paume;
  // un doigt est tendu si son bout est plus loin du poignet que sa base
  const tendus = [[8, 5], [12, 9], [16, 13], [20, 17]]
    .filter(([bout, base]) => distance(points[bout], points[0]) > distance(points[base], points[0]) * 1.35).length;
  const pouceTendu = distance(points[4], points[0]) > distance(points[2], points[0]) * 1.25;
  return {
    paume,
    pince,
    doigts: tendus + (pouceTendu ? 1 : 0),
    ouverte: tendus === 4 && pouceTendu && pince > 0.7,
    index: { x: points[8].x, y: points[8].y },
    centre: { x: (points[0].x + points[9].x) / 2, y: (points[0].y + points[9].y) / 2 },
    // l'inclinaison du poignet : l'angle de la ligne poignet → base du majeur
    angle: Math.atan2(points[9].y - points[0].y, points[9].x - points[0].x),
  };
}

function ecartAngles(a, b) {
  let d = a - b;
  while (d > Math.PI) d -= 2 * Math.PI;
  while (d < -Math.PI) d += 2 * Math.PI;
  return d;
}

/** L'état que l'on garde d'une image à l'autre. */
export function etatVide() {
  return { mains: [], t: 0, pince: [false, false], rotation: [0, 0], ouverteDepuis: 0, ecart: 0, dernier: -10, balayage: 0 };
}

/**
 * `mains` : tableau de tableaux de 21 points (une entrée par main vue), `t` en secondes.
 * Rend la liste des gestes de cette image : {type, ...}. Types :
 *   curseur {x, y, pince}        — la position de l'index de la main principale, à chaque image
 *   pince_debut / pince_fin {x, y}
 *   rotation {delta}             — poignet tourné pendant une pince
 *   zoom {facteur}               — les deux mains écartées ou rapprochées
 *   balayage {sens}              — main ouverte lancée horizontalement
 *   reveil                       — main ouverte et immobile pendant trois secondes
 */
export function lire(etat, mains, t) {
  const gestes = [];
  const dt = etat.t ? Math.max(1e-3, t - etat.t) : 1e-3;
  const mesures = mains.map(mesurer);
  const precedentes = etat.mains;

  if (!mesures.length) {                                        // plus de main : tout retombe
    for (let i = 0; i < 2; i++) if (etat.pince[i]) { gestes.push({ type: "pince_fin", main: i }); etat.pince[i] = false; }
    etat.ouverteDepuis = 0; etat.ecart = 0;
    etat.mains = []; etat.t = t;
    return gestes;
  }

  const principale = mesures[0];
  gestes.push({ type: "curseur", x: principale.index.x, y: principale.index.y, pince: etat.pince[0], doigts: principale.doigts });

  mesures.forEach((m, i) => {
    if (i > 1) return;
    const avant = precedentes[i];
    // pincer : attraper ; relâcher demande de rouvrir franchement (hystérésis)
    if (!etat.pince[i] && m.pince < SEUILS.pince) {
      etat.pince[i] = true;
      gestes.push({ type: "pince_debut", main: i, x: m.index.x, y: m.index.y });
    } else if (etat.pince[i] && m.pince > SEUILS.relache) {
      etat.pince[i] = false;
      gestes.push({ type: "pince_fin", main: i, x: m.index.x, y: m.index.y });
    }
    // tourner le poignet pendant la pince : l'objet tourne d'autant. On cumule les petits écarts d'une image à
    // l'autre (un poignet tourne doucement : 0,03 rad par image) et on rend le total dès qu'il sort du tremblement.
    if (etat.pince[i] && avant) {
      etat.rotation[i] += ecartAngles(m.angle, avant.angle);
      if (Math.abs(etat.rotation[i]) > SEUILS.rotation_min) {
        gestes.push({ type: "rotation", delta: etat.rotation[i], main: i });
        etat.rotation[i] = 0;
      }
    } else if (!etat.pince[i]) {
      etat.rotation[i] = 0;
    }
  });

  // les deux mains : écarter pour agrandir, rapprocher pour réduire
  if (mesures.length >= 2) {
    const ecart = distance(mesures[0].centre, mesures[1].centre);
    if (etat.ecart && Math.abs(ecart - etat.ecart) > SEUILS.zoom_min) {
      gestes.push({ type: "zoom", facteur: ecart / etat.ecart, ecart });
    }
    etat.ecart = ecart;
  } else {
    etat.ecart = 0;
  }

  // balayer : main ouverte, lancée horizontalement
  const avant0 = precedentes[0];
  if (avant0) {
    const vx = (principale.centre.x - avant0.centre.x) / dt;
    const vy = (principale.centre.y - avant0.centre.y) / dt;
    const vitesse = Math.hypot(vx, vy);
    if (principale.doigts >= 4 && Math.abs(vx) > SEUILS.balayage_vitesse && Math.abs(vx) > Math.abs(vy) * 1.5) {
      etat.balayage += Math.abs(principale.centre.x - avant0.centre.x);
      if (etat.balayage > SEUILS.balayage_course && t - etat.dernier > 0.6) {   // un balayage à la fois
        gestes.push({ type: "balayage", sens: vx > 0 ? "droite" : "gauche" });
        etat.balayage = 0;
        etat.dernier = t;
      }
    } else {
      etat.balayage = 0;
    }
    // main ouverte et immobile trois secondes : réveil
    if (principale.ouverte && vitesse < SEUILS.immobile) {
      if (!etat.ouverteDepuis) etat.ouverteDepuis = t;
      else if (t - etat.ouverteDepuis >= SEUILS.main_ouverte_s && t - etat.dernier > SEUILS.main_ouverte_s) {
        gestes.push({ type: "reveil", tenue: +(t - etat.ouverteDepuis).toFixed(2) });
        etat.dernier = t;
        etat.ouverteDepuis = 0;
      }
    } else {
      etat.ouverteDepuis = 0;
    }
  }

  etat.mains = mesures;
  etat.t = t;
  return gestes;
}
