// Le globe (v3, consigne 7) : une Terre holographique en fil de fer qui tourne, la Station spatiale en direct
// avec sa trajectoire, et les séismes du jour en impulsions.
//
// Les côtes viennent de vendor/terre-110m.json (Natural Earth 110 m, domaine public), ramenées au dixième de degré :
// 5 121 points, 55 Ko, largement assez pour un hologramme. Aucune image satellite, aucune tuile à télécharger.
// La position de l'utilisateur n'est JAMAIS utilisée : rien ici ne lit navigator.geolocation.
import * as THREE from "three";

const RAYON = 1;
const COTES = "/hud/vendor/terre-110m.json";

/** latitude/longitude en degrés → point sur la sphère (rayon `r`). Longitude 0 face à la caméra. */
export function surLaSphere(lat, lon, r = RAYON) {
  const phi = (90 - lat) * Math.PI / 180, theta = (lon + 180) * Math.PI / 180;
  return new THREE.Vector3(-r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta));
}

function grille() {                       // méridiens et parallèles
  const points = [];
  for (let lon = -180; lon < 180; lon += 30)
    for (let lat = -90; lat < 90; lat += 5) {
      points.push(surLaSphere(lat, lon), surLaSphere(lat + 5, lon));
    }
  for (let lat = -60; lat <= 60; lat += 30)
    for (let lon = -180; lon < 180; lon += 5) {
      points.push(surLaSphere(lat, lon), surLaSphere(lat, lon + 5));
    }
  const g = new THREE.BufferGeometry().setFromPoints(points);
  return g;
}

const SOMMET_HOLO = `
  varying vec3 vNormale; varying vec3 vVue; varying float vHaut;
  void main(){ vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vNormale = normalize(normalMatrix * normal); vVue = normalize(-mv.xyz); vHaut = position.y;
    gl_Position = projectionMatrix * mv; }`;

const FRAGMENT_HOLO = `
  uniform vec3 uCouleur; uniform float uTemps; uniform float uApparition;
  varying vec3 vNormale; varying vec3 vVue; varying float vHaut;
  void main(){
    float face = abs(dot(normalize(vNormale), normalize(vVue)));
    float bord = pow(1.0 - face, 2.0);
    float balayage = 0.6 + 0.4 * sin(vHaut * 40.0 - uTemps * 2.0);
    gl_FragColor = vec4(uCouleur * (0.5 + bord * 2.0), (0.06 + bord * 0.5) * balayage * uApparition);
  }`;

export function creerGlobe(U) {
  const groupe = new THREE.Group();
  groupe.visible = false;
  const uniformes = { uTemps: U.uTemps, uCouleur: U.uCouleur, uApparition: { value: 0 } };
  const tourne = new THREE.Group();            // ce qui tourne avec la Terre (côtes, grille, marqueurs)
  groupe.add(tourne);

  // l'atmosphère : une sphère translucide vue de l'intérieur du bord
  const atmosphere = new THREE.Mesh(new THREE.SphereGeometry(RAYON * 1.005, 48, 32), new THREE.ShaderMaterial({
    uniforms: uniformes, vertexShader: SOMMET_HOLO, fragmentShader: FRAGMENT_HOLO,
    transparent: true, depthWrite: false, side: THREE.FrontSide, blending: THREE.AdditiveBlending }));
  groupe.add(atmosphere);

  const matiereTrait = new THREE.LineBasicMaterial({ transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false });
  const matiereGrille = new THREE.LineBasicMaterial({ transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false });
  tourne.add(new THREE.LineSegments(grille(), matiereGrille));
  const cotes = new THREE.LineSegments(new THREE.BufferGeometry(), matiereTrait);
  tourne.add(cotes);

  // la Station spatiale : un point, son halo, et sa trajectoire
  const station = new THREE.Group();
  station.visible = false;
  const pointStation = new THREE.Mesh(new THREE.SphereGeometry(0.022, 12, 8),
    new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }));
  const haloStation = new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 8),
    new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.35, blending: THREE.AdditiveBlending, depthWrite: false }));
  const trajectoire = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({
    transparent: true, opacity: 0.55, blending: THREE.AdditiveBlending, depthWrite: false }));
  station.add(pointStation, haloStation, trajectoire);
  tourne.add(station);

  // les séismes : TOUS dans un seul objet, animés dans le shader. Un maillage par séisme coûtait 0,84 ms par
  // image pour quarante d'entre eux (mesuré le 20/09) ; ici c'est un seul dessin, quel que soit leur nombre.
  const seismes = new THREE.Mesh(new THREE.BufferGeometry(), new THREE.ShaderMaterial({
    uniforms: { uTemps: U.uTemps, uCouleur: U.uCouleur, uApparition: uniformes.uApparition },
    transparent: true, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending,
    vertexShader: `
      uniform float uTemps;
      attribute vec3 aCentre; attribute vec3 aDroite; attribute vec3 aHaut; attribute vec2 aCoin;
      attribute float aPhase; attribute float aMagnitude;
      varying vec2 vCoin; varying float vPhase;
      void main(){
        float phase = fract(uTemps * 0.55 + aPhase);
        float taille = (0.05 + aMagnitude * 0.018) * (0.4 + phase * 1.6);
        vec3 p = aCentre + (aDroite * aCoin.x + aHaut * aCoin.y) * taille;
        vCoin = aCoin; vPhase = phase;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
      }`,
    fragmentShader: `
      uniform vec3 uCouleur; uniform float uApparition;
      varying vec2 vCoin; varying float vPhase;
      void main(){
        float d = length(vCoin);
        float anneau = smoothstep(0.55, 0.75, d) * smoothstep(1.0, 0.8, d);    // une couronne, pas un disque
        if (anneau < 0.02) discard;
        gl_FragColor = vec4(uCouleur * 1.6, anneau * (1.0 - vPhase) * 0.9 * uApparition);
      }`,
  }));
  tourne.add(seismes);

  const E = { cible: 0, apparition: 0, rotation: 0, vitesse: 0.12, etat: "vide", cotesPretes: false,
              seismes: [], station: null, echelleBase: 1 };

  async function chargerCotes() {
    if (E.cotesPretes) return;
    const d = await (await fetch(COTES)).json();
    const points = [];
    for (const trait of d.traits) {
      for (let i = 0; i + 3 < trait.length; i += 2) {
        points.push(surLaSphere(trait[i + 1], trait[i], RAYON * 1.002));
        points.push(surLaSphere(trait[i + 3], trait[i + 2], RAYON * 1.002));
      }
    }
    cotes.geometry.dispose();
    cotes.geometry = new THREE.BufferGeometry().setFromPoints(points);
    E.cotesPretes = true;
    return points.length;
  }

  return {
    objet: groupe,
    placer(x, y, z, echelle) { groupe.position.set(x, y, z); E.echelleBase = echelle; groupe.scale.setScalar(echelle); },
    get visible() { return groupe.visible && E.apparition > 0.01; },
    get etat() {
      return { etat: E.etat, visible: this.visible, rotation: +E.rotation.toFixed(3),
               cotes: cotes.geometry.attributes.position ? cotes.geometry.attributes.position.count : 0,
               station: E.station, seismes: E.seismes.length, apparition: +E.apparition.toFixed(2) };
    },
    /** Où le point (lat, lon) se trouve à l'écran, pour les tests. */
    ecran(lat, lon, camera) {
      const monde = surLaSphere(lat, lon).applyMatrix4(tourne.matrixWorld);
      const centre = groupe.getWorldPosition(new THREE.Vector3());
      // « devant » : la normale du point regarde vers la caméra (le reste est caché par le globe)
      const normale = monde.clone().sub(centre).normalize();
      const versCamera = camera.position.clone().sub(centre).normalize();
      const p = monde.clone().project(camera);
      return { x: (p.x + 1) / 2 * innerWidth, y: (1 - p.y) / 2 * innerHeight, devant: normale.dot(versCamera) > 0 };
    },
    async afficher() {
      const points = await chargerCotes();
      groupe.visible = true;
      E.cible = 1;
      E.etat = "affiche";
      return { cotes: cotes.geometry.attributes.position.count, points };
    },
    cacher() { E.cible = 0; if (E.etat !== "vide") E.etat = "disparition"; },
    /** `positions` : jusqu'à maintenant (la dernière est la position actuelle) ; `avenir` : la suite du trajet. */
    placerStation(positions, avenir = []) {
      if (!positions || !positions.length) { station.visible = false; E.station = null; return; }
      const maintenant = positions[positions.length - 1];
      positions = positions.concat(avenir || []);
      const h = RAYON * (1 + (maintenant.altitude_km || 420) / 6371);
      pointStation.position.copy(surLaSphere(maintenant.lat, maintenant.lon, h));
      haloStation.position.copy(pointStation.position);
      trajectoire.geometry.dispose();
      trajectoire.geometry = new THREE.BufferGeometry().setFromPoints(
        positions.map(p => surLaSphere(p.lat, p.lon, RAYON * (1 + (p.altitude_km || 420) / 6371))));
      station.visible = true;
      E.station = { lat: maintenant.lat, lon: maintenant.lon, altitude_km: maintenant.altitude_km, points: positions.length };
      E.etat = "station";
    },
    /** `liste` : [{lat, lon, magnitude, lieu}] — tous les séismes dans un seul objet. */
    placerSeismes(liste) {
      liste = liste || [];
      E.seismes = liste.map(s => ({ magnitude: s.magnitude || 3, lieu: s.lieu || "", lat: s.lat, lon: s.lon }));
      const n = liste.length;
      const coins = [[-1, -1], [1, -1], [1, 1], [-1, 1]];
      const pos = new Float32Array(n * 4 * 3), centre = new Float32Array(n * 4 * 3);
      const droite = new Float32Array(n * 4 * 3), haut = new Float32Array(n * 4 * 3);
      const coin = new Float32Array(n * 4 * 2), phase = new Float32Array(n * 4), magnitude = new Float32Array(n * 4);
      const index = [];
      const nord = new THREE.Vector3(0, 1, 0), d = new THREE.Vector3(), h = new THREE.Vector3();
      liste.forEach((s, i) => {
        const c = surLaSphere(s.lat, s.lon, RAYON * 1.004);
        d.copy(nord).cross(c).normalize();                  // deux directions tangentes à la sphère
        if (d.lengthSq() < 0.01) d.set(1, 0, 0);
        h.copy(c).cross(d).normalize();
        const p = Math.random();
        for (let k = 0; k < 4; k++) {
          const j = i * 4 + k;
          centre.set([c.x, c.y, c.z], j * 3);
          droite.set([d.x, d.y, d.z], j * 3);
          haut.set([h.x, h.y, h.z], j * 3);
          pos.set([c.x, c.y, c.z], j * 3);                  // la vraie position est calculée dans le shader
          coin.set(coins[k], j * 2);
          phase[j] = p;
          magnitude[j] = s.magnitude || 3;
        }
        index.push(i * 4, i * 4 + 1, i * 4 + 2, i * 4, i * 4 + 2, i * 4 + 3);
      });
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      g.setAttribute("aCentre", new THREE.BufferAttribute(centre, 3));
      g.setAttribute("aDroite", new THREE.BufferAttribute(droite, 3));
      g.setAttribute("aHaut", new THREE.BufferAttribute(haut, 3));
      g.setAttribute("aCoin", new THREE.BufferAttribute(coin, 2));
      g.setAttribute("aPhase", new THREE.BufferAttribute(phase, 1));
      g.setAttribute("aMagnitude", new THREE.BufferAttribute(magnitude, 1));
      g.setIndex(index);
      g.boundingSphere = new THREE.Sphere(new THREE.Vector3(), RAYON * 1.4);
      seismes.geometry.dispose();
      seismes.geometry = g;
      seismes.visible = n > 0;
      E.etat = "seismes";
      return n;
    },
    animer(dt, tS) {
      E.apparition += (E.cible - E.apparition) * Math.min(1, dt * (E.cible ? 2.6 : 6));
      if (E.cible === 0 && E.apparition < 0.02) { groupe.visible = false; E.apparition = 0; E.etat = "cache"; }
      if (!groupe.visible) return;
      uniformes.uApparition.value = E.apparition;
      matiereTrait.color.copy(U.uCouleur.value);
      matiereTrait.opacity = E.apparition * 0.95;
      matiereGrille.color.copy(U.uCouleur.value);
      matiereGrille.opacity = E.apparition * 0.16;
      haloStation.material.color.copy(U.uCouleur.value);
      trajectoire.material.color.copy(U.uCouleur.value);
      trajectoire.material.opacity = E.apparition * 0.5;
      pointStation.material.opacity = E.apparition * (0.75 + 0.25 * Math.sin(tS * 6));
      haloStation.scale.setScalar(1 + 0.25 * Math.sin(tS * 3));
      E.rotation += dt * E.vitesse;
      tourne.rotation.y = E.rotation;
      groupe.scale.setScalar(E.echelleBase * (0.85 + 0.15 * E.apparition));
    },
  };
}
