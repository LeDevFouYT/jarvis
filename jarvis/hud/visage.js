// Le visage (v3, consigne 2) : un nuage de points three.js qui naît des anneaux du réacteur, forme un visage, parle
// au rythme de la voix de Jarvis (niveau sonore diffusé 20 fois par seconde), cligne des yeux, puis redevient
// réacteur. Un seul THREE.Points, tout calculé dans le shader : aucune allocation par image.
//
// Chaque point a deux places : `aDepart` sur un anneau du réacteur, `position` sur le visage. `uForme` (0 réacteur,
// 1 visage) les mélange, avec un tourbillon au milieu de la transition. Attributs d'animation : `aLevre` (+1 lèvre du
// haut, -1 lèvre du bas), `aMachoire` (0 à 1, le bas du visage qui suit la bouche), `aPaupiere` (+1 / -1, les
// paupières qui se ferment vers le centre de l'œil), `aCentreOeil` (y du centre de l'œil), `aEclat` (luminosité).
import * as THREE from "three";

const NB = 7000;

function aleatoire(graine) { let s = graine >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }

// le visage : une tête ellipsoïde vue de face, creusée aux yeux et à la bouche, et ses traits en points plus serrés
function genererVisage() {
  const hasard = aleatoire(20260919);
  const pos = new Float32Array(NB * 3), depart = new Float32Array(NB * 3);
  const levre = new Float32Array(NB), machoire = new Float32Array(NB), paupiere = new Float32Array(NB),
    centreOeil = new Float32Array(NB), eclat = new Float32Array(NB), graine = new Float32Array(NB);
  const RX = 1.18, RY = 1.55, RZ = 1.0;
  const surface = (x, y) => RZ * Math.sqrt(Math.max(0, 1 - (x * x) / (RX * RX) - (y * y) / (RY * RY)));
  const OEILX = 0.42, OEILY = 0.3, BOUCHE_Y = -0.66;
  let i = 0;
  const poser = (x, y, z, { l = 0, m = 0, p = 0, co = 0, e = 0.55 } = {}) => {
    if (i >= NB) return;
    pos[i * 3] = x; pos[i * 3 + 1] = y; pos[i * 3 + 2] = z;
    levre[i] = l; machoire[i] = m; paupiere[i] = p; centreOeil[i] = co; eclat[i] = e; graine[i] = hasard();
    i++;
  };
  const machoireDe = y => Math.min(1, Math.max(0, (BOUCHE_Y - 0.06 - y) / 0.7));

  // les traits d'abord (ils doivent exister quoi qu'il arrive), la peau remplit le reste
  for (const cote of [-1, 1]) {
    const cx = cote * OEILX;
    for (let k = 0; k < 260; k++) {                                   // l'œil : paupières en amande
      const a = hasard() * Math.PI * 2, haut = Math.sin(a) > 0;
      const x = cx + Math.cos(a) * 0.2, y = OEILY + Math.sin(a) * 0.085;
      poser(x, y, surface(x, y) + 0.02, { p: haut ? 1 : -1, co: OEILY, e: 0.9 });
    }
    for (let k = 0; k < 90; k++) {                                    // l'iris, lumineux
      const a = hasard() * Math.PI * 2, r = Math.sqrt(hasard()) * 0.06;
      const x = cx + Math.cos(a) * r, y = OEILY + Math.sin(a) * r;
      poser(x, y, surface(x, y) + 0.03, { p: 0.001, co: OEILY, e: 1.4 });
    }
    for (let k = 0; k < 140; k++) {                                   // le sourcil
      const t = hasard(), x = cx + (t - 0.5) * 0.46 * cote, y = OEILY + 0.2 + Math.sin(t * Math.PI) * 0.05 - (t - 0.5) * 0.02;
      poser(x, y, surface(x, y) + 0.03, { e: 0.8 });
    }
  }
  for (let k = 0; k < 260; k++) {                                     // l'arête du nez et les narines
    const t = hasard(), y = 0.2 - t * 0.5, x = (hasard() - 0.5) * 0.06 * (0.4 + t);
    poser(x, y, surface(x, y) + 0.05 + t * 0.14, { e: 0.75 });
  }
  for (let k = 0; k < 120; k++) {
    const a = hasard() * Math.PI, cote = hasard() < 0.5 ? -1 : 1;
    const x = cote * (0.09 + Math.cos(a) * 0.05), y = -0.33 + Math.sin(a) * 0.03;
    poser(x, y, surface(x, y) + 0.14, { e: 0.8 });
  }
  for (let k = 0; k < 700; k++) {                                     // les lèvres : arc de Cupidon en haut, lèvre pleine en bas
    const haut = hasard() < 0.5, t = hasard() * 2 - 1, x = t * 0.42;
    const courbe = 1 - t * t;
    const y = haut ? BOUCHE_Y + 0.03 + courbe * 0.05 - Math.abs(Math.sin(t * Math.PI * 1.5)) * 0.012 + hasard() * 0.035
                   : BOUCHE_Y - 0.03 - courbe * 0.07 - hasard() * 0.035;
    poser(x, y, surface(x, y) + 0.06 * courbe, { l: haut ? 1 : -1, m: haut ? 0 : 0.35, e: 1.0 });
  }
  // la peau : points tirés sur l'ellipsoïde, face avant, plus clairsemés sur les bords
  while (i < NB) {
    const x = (hasard() * 2 - 1) * RX, y = (hasard() * 2 - 1) * RY;
    if ((x * x) / (RX * RX) + (y * y) / (RY * RY) > 1) continue;
    const dansOeil = Math.hypot(Math.abs(x) - OEILX, (y - OEILY) * 2.2) < 0.23;
    const dansBouche = Math.abs(x) < 0.4 && Math.abs(y - BOUCHE_Y) < 0.1;
    if (dansOeil || dansBouche) continue;
    const z = surface(x, y);
    const bord = 1 - z / RZ;
    if (hasard() < bord * 0.55) continue;                            // les tempes et le menton, moins denses
    poser(x, y, z, { m: machoireDe(y), e: 0.3 + (1 - bord) * 0.35 });
  }

  // les places de départ : les anneaux du réacteur (même repère que ses anneaux, dans le plan face à la caméra)
  const RAYONS = [0.66, 0.86, 1.48, 1.7, 2.04, 2.37, 2.53];
  for (let k = 0; k < NB; k++) {
    const r = RAYONS[Math.floor(graine[k] * RAYONS.length)] + (hasard() - 0.5) * 0.05, a = hasard() * Math.PI * 2;
    depart[k * 3] = Math.cos(a) * r; depart[k * 3 + 1] = Math.sin(a) * r; depart[k * 3 + 2] = (hasard() - 0.5) * 0.05;
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("aDepart", new THREE.BufferAttribute(depart, 3));
  g.setAttribute("aLevre", new THREE.BufferAttribute(levre, 1));
  g.setAttribute("aMachoire", new THREE.BufferAttribute(machoire, 1));
  g.setAttribute("aPaupiere", new THREE.BufferAttribute(paupiere, 1));
  g.setAttribute("aCentreOeil", new THREE.BufferAttribute(centreOeil, 1));
  g.setAttribute("aEclat", new THREE.BufferAttribute(eclat, 1));
  g.setAttribute("aGraine", new THREE.BufferAttribute(graine, 1));
  return g;
}

export function creerVisage(U) {
  const V = { uForme: { value: 0 }, uBouche: { value: 0 }, uArrondi: { value: 0 }, uClignement: { value: 0 } };
  const points = new THREE.Points(genererVisage(), new THREE.ShaderMaterial({
    uniforms: { uTemps: U.uTemps, uCouleur: U.uCouleur, uPixelRatio: U.uPixelRatio, uIntensite: U.uIntensite, ...V },
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    vertexShader: `
      uniform float uTemps; uniform float uPixelRatio; uniform float uForme; uniform float uBouche; uniform float uArrondi; uniform float uClignement;
      attribute vec3 aDepart; attribute float aLevre; attribute float aMachoire; attribute float aPaupiere; attribute float aCentreOeil;
      attribute float aEclat; attribute float aGraine;
      varying float vAlpha; varying float vEclat;
      void main(){
        vec3 v = position;
        // la bouche : la lèvre du haut monte un peu, celle du bas et la mâchoire descendent ; arrondie, elle se resserre
        float haut = step(0.5, aLevre), bas = step(0.5, -aLevre);
        v.y += haut * uBouche * 0.035 - bas * uBouche * 0.11 - aMachoire * uBouche * 0.13;
        v.x *= 1.0 - abs(aLevre) * uArrondi * 0.28;
        v.z += abs(aLevre) * uArrondi * 0.05;
        // les paupières se referment vers le centre de l'œil
        if (abs(aPaupiere) > 0.5) v.y = mix(v.y, aCentreOeil, uClignement);
        // un léger frémissement : le visage est fait de lumière
        v += vec3(sin(uTemps * 1.3 + aGraine * 40.0), cos(uTemps * 1.1 + aGraine * 31.0), 0.0) * 0.006;
        // la transition : chaque point quitte son anneau à son heure, et tourbillonne à mi-chemin
        float f = smoothstep(aGraine * 0.35, aGraine * 0.35 + 0.65, uForme);
        vec3 p = mix(aDepart, v, f);
        float tourbillon = sin(f * 3.14159) * (0.25 + aGraine * 0.5);
        float a = tourbillon * 2.2 + aGraine * 6.28;
        p += vec3(cos(a), sin(a), sin(a * 1.7)) * tourbillon * 0.35;
        vec4 mv = modelViewMatrix * vec4(p, 1.0);
        gl_PointSize = uPixelRatio * (1.6 + aEclat * 2.2) * (11.0 / -mv.z);
        vAlpha = smoothstep(0.0, 0.15, uForme) * (0.55 + 0.45 * sin(uTemps * 2.0 + aGraine * 20.0) * 0.5 + 0.25);
        vEclat = aEclat;
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: `
      uniform vec3 uCouleur; uniform float uIntensite; varying float vAlpha; varying float vEclat;
      void main(){
        float d = length(gl_PointCoord - 0.5);
        vec3 c = mix(uCouleur, vec3(1.0), clamp(vEclat - 0.8, 0.0, 0.6));
        gl_FragColor = vec4(c, smoothstep(0.5, 0.0, d) * vAlpha * vEclat * (0.6 + min(uIntensite, 1.2) * 0.5));
      }`,
  }));
  points.frustumCulled = false;
  points.visible = false;

  const E = { forme: 0, cible: 0, bouche: 0, prochainClin: 3, clin: -1 };
  return {
    objet: points,
    set actif(v) { E.cible = v ? 1 : 0; },
    get actif() { return E.cible === 1; },
    get forme() { return E.forme; },
    get bouche() { return V.uBouche.value; },
    get clignement() { return V.uClignement.value; },
    // appelé à chaque image par le réacteur : `niveau` = niveau sonore de la voix (0 à 1), `tS` = temps en secondes
    animer(dt, tS, niveau) {
      E.forme += Math.sign(E.cible - E.forme) * Math.min(Math.abs(E.cible - E.forme), dt / 1.6);   // 1,6 s de transition
      V.uForme.value = E.forme;
      points.visible = E.forme > 0.001;
      if (!points.visible) return;
      // la bouche suit la voix : ouverture rapide, fermeture plus douce ; l'arrondi varie pour éviter l'effet de clapet
      const cible = Math.min(1, niveau * 1.15);
      E.bouche += (cible - E.bouche) * (cible > E.bouche ? 0.55 : 0.25);
      V.uBouche.value = E.bouche;
      V.uArrondi.value = E.bouche * (0.5 + 0.5 * Math.sin(tS * 6.3) * Math.sin(tS * 2.1));
      // un clignement toutes les 3 à 6 s, 0,16 s
      if (E.clin < 0 && tS > E.prochainClin) E.clin = tS;
      if (E.clin >= 0) {
        const p = (tS - E.clin) / 0.16;
        V.uClignement.value = p < 0.5 ? p * 2 : Math.max(0, 2 - p * 2);
        if (p >= 1) { E.clin = -1; V.uClignement.value = 0; E.prochainClin = tS + 3 + Math.random() * 3; }
      }
    },
  };
}
