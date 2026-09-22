// L'hologramme (v3, consigne 4) : le .glb sculpté par Hunyuan3D, affiché au-dessus de la table en matière
// translucide, traversé de lignes de balayage, qui tourne lentement et apparaît « en impression » de bas en haut.
//
// Le fichier est lu ici même : un .glb est un entête, un bloc JSON et un bloc binaire. On n'en prend que les
// positions, les normales et les triangles (la matière est la nôtre), ce qui évite d'embarquer un chargeur complet.
import * as THREE from "three";

const TYPES = { 5120: Int8Array, 5121: Uint8Array, 5122: Int16Array, 5123: Uint16Array, 5125: Uint32Array, 5126: Float32Array };
const COMPOSANTES = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4, MAT4: 16 };

export function lireGlb(donnees) {
  const vue = new DataView(donnees);
  if (vue.getUint32(0, true) !== 0x46546c67) throw new Error("ce fichier n'est pas un .glb");
  let position = 12, json = null, binaire = null;
  while (position < vue.byteLength) {
    const taille = vue.getUint32(position, true), genre = vue.getUint32(position + 4, true);
    const bloc = donnees.slice(position + 8, position + 8 + taille);
    if (genre === 0x4e4f534a) json = JSON.parse(new TextDecoder().decode(bloc));
    else if (genre === 0x004e4942) binaire = bloc;
    position += 8 + taille + (taille % 4 ? 4 - (taille % 4) : 0);
  }
  if (!json || !binaire) throw new Error(".glb incomplet");

  const lire = i => {
    const a = json.accessors[i], v = json.bufferViews[a.bufferView];
    const Type = TYPES[a.componentType], n = COMPOSANTES[a.type];
    const debut = (v.byteOffset || 0) + (a.byteOffset || 0);
    if (v.byteStride && v.byteStride !== n * Type.BYTES_PER_ELEMENT) {     // données entrelacées : on désentrelace
      const sortie = new Type(a.count * n), source = new DataView(binaire, debut);
      const lecture = { 5126: "getFloat32", 5125: "getUint32", 5123: "getUint16", 5121: "getUint8" }[a.componentType];
      for (let k = 0; k < a.count; k++)
        for (let c = 0; c < n; c++) sortie[k * n + c] = source[lecture](k * v.byteStride + c * Type.BYTES_PER_ELEMENT, true);
      return sortie;
    }
    return new Type(binaire, debut, a.count * n);
  };

  const morceaux = [];
  for (const maille of json.meshes || []) {
    for (const p of maille.primitives || []) {
      if (p.attributes.POSITION === undefined) continue;
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(lire(p.attributes.POSITION), 3));
      if (p.attributes.NORMAL !== undefined) g.setAttribute("normal", new THREE.BufferAttribute(lire(p.attributes.NORMAL), 3));
      if (p.indices !== undefined) g.setIndex(new THREE.BufferAttribute(lire(p.indices), 1));
      if (!g.attributes.normal) g.computeVertexNormals();
      morceaux.push(g);
    }
  }
  if (!morceaux.length) throw new Error("aucun maillage dans ce .glb");
  return morceaux;
}

const SOMMET = `
  uniform float uTemps; uniform float uImpression; uniform float uApparition; uniform float uHauteur;
  varying vec3 vNormale; varying vec3 vVue; varying vec3 vLocal;
  void main(){
    vLocal = position;
    // l'impression : la tranche en cours de « dépôt » tremble un peu avant de se fixer
    vec3 p = position;
    float bord = 1.0 - smoothstep(0.0, 0.12, uImpression - position.y / uHauteur);
    p.x += sin(uTemps * 30.0 + position.y * 40.0) * 0.012 * bord;
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    vNormale = normalize(normalMatrix * normal);
    vVue = normalize(-mv.xyz);
    gl_Position = projectionMatrix * mv;
  }`;

const FRAGMENT = `
  uniform vec3 uCouleur; uniform float uTemps; uniform float uImpression; uniform float uApparition; uniform float uIntensite;
  uniform float uHauteur;
  varying vec3 vNormale; varying vec3 vVue; varying vec3 vLocal;
  void main(){
    float hauteur = vLocal.y / uHauteur;                  // 0 au pied de l'objet, 1 à son sommet
    if (hauteur > uImpression) discard;                   // pas encore imprimé
    float face = abs(dot(normalize(vNormale), normalize(vVue)));
    float bord = pow(1.0 - face, 2.2);                    // la lumière s'accroche aux silhouettes
    float balayage = 0.55 + 0.45 * sin((vLocal.y * 90.0) - uTemps * 3.0);
    float bande = smoothstep(0.035, 0.0, uImpression - hauteur) * step(uImpression, 0.999);  // la ligne d'impression
    float scintillement = 0.94 + 0.06 * sin(uTemps * 21.0 + vLocal.y * 7.0);
    float a = (0.30 + bord * 1.1) * balayage * scintillement * uApparition;
    vec3 c = uCouleur * (0.9 + bord * 2.2) + vec3(1.0) * (bord * 0.35 + bande * 1.6);
    gl_FragColor = vec4(c * (0.8 + min(uIntensite, 1.2) * 0.3), clamp(a + bande * 0.9, 0.0, 1.0));
  }`;

export function creerHologramme(U) {
  const groupe = new THREE.Group();
  groupe.visible = false;
  const uniformes = {
    uTemps: U.uTemps, uCouleur: U.uCouleur, uIntensite: U.uIntensite,
    uImpression: { value: 0 }, uApparition: { value: 0 }, uHauteur: { value: 1 },
  };
  const matiere = new THREE.ShaderMaterial({
    uniforms: uniformes, vertexShader: SOMMET, fragmentShader: FRAGMENT,
    transparent: true, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending,
  });
  // le socle : un disque de projection sous l'objet
  const socle = new THREE.Mesh(new THREE.RingGeometry(0.58, 0.66, 96), new THREE.MeshBasicMaterial({
    transparent: true, opacity: 0, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false }));
  socle.rotation.x = -Math.PI / 2;
  socle.position.y = 0.002;
  groupe.add(socle);

  const E = { baseY: 0, echelleBase: 1, echelleGeste: 1, glissementX: 0, glissementY: 0, objet: "", url: "", etat: "vide", impression: 0, apparition: 0, cible: 0, rotation: 0, vitesse: 0.35, maille: null };

  function poser(geometries) {
    if (E.maille) { groupe.remove(E.maille); E.maille.geometry.dispose(); }
    const fusion = geometries.length === 1 ? geometries[0] : geometries[0];      // Hunyuan3D sort un seul maillage
    fusion.computeBoundingBox();
    const boite = fusion.boundingBox, centre = new THREE.Vector3(), taille = new THREE.Vector3();
    boite.getCenter(centre); boite.getSize(taille);
    const echelle = 1 / Math.max(taille.x, taille.y, taille.z);                  // objet ramené dans un cube de 1
    fusion.translate(-centre.x, -boite.min.y, -centre.z);                        // posé sur son socle, à l'origine
    fusion.scale(echelle, echelle, echelle);
    uniformes.uHauteur.value = Math.max(0.001, taille.y * echelle);
    fusion.computeBoundingBox();                                                 // après transformation, sinon périmé
    fusion.computeBoundingSphere();
    const maille = new THREE.Mesh(fusion, matiere);
    E.maille = maille;
    groupe.add(maille);
  }

  return {
    objet: groupe,
    placer(x, y, z, echelle) { groupe.position.set(x, y, z); E.baseY = y; E.echelleBase = echelle; groupe.scale.setScalar(echelle); },
    get etat() { return E.etat; },
    get objetAffiche() { return E.objet; },
    get impression() { return E.impression; },
    get visible() { return groupe.visible && E.apparition > 0.01; },
    get sommets() { return E.maille ? E.maille.geometry.attributes.position.count : 0; },
    get rotation() { return E.rotation; },
    get boite() {                                            // pour les tests : l'objet dans le monde
      if (!E.maille) return null;
      const b = new THREE.Box3().setFromObject(groupe);
      const l = E.maille.geometry.boundingBox;
      return { min: b.min.toArray().map(v => +v.toFixed(2)), max: b.max.toArray().map(v => +v.toFixed(2)),
               local: [l.min.toArray().map(v => +v.toFixed(2)), l.max.toArray().map(v => +v.toFixed(2))],
               visible: groupe.visible, echelle: groupe.scale.x, hauteurUnif: uniformes.uHauteur.value,
               apparition: uniformes.uApparition.value, impression: uniformes.uImpression.value };
    },
    tourner(delta) { E.rotation += delta; },                 // les gestes (consigne 5)
    echelle(e) { E.echelleGeste = Math.min(2.5, Math.max(0.4, e)); },
    deplacer(dx, dy) { E.glissementX += dx; E.glissementY += dy; },
    get reglageGeste() { return { echelle: E.echelleGeste, x: E.glissementX, y: E.glissementY }; },
    vitesse(v) { E.vitesse = v; },
    async afficher(url, objet = "") {
      E.etat = "chargement"; E.url = url; E.objet = objet;
      const donnees = await (await fetch(url)).arrayBuffer();
      poser(lireGlb(donnees));
      E.impression = 0; E.cible = 1; E.rotation = 0; E.echelleGeste = 1; E.glissementX = 0; E.glissementY = 0;
      groupe.visible = true;
      E.etat = "impression";
      return { sommets: this.sommets, octets: donnees.byteLength };
    },
    cacher() { E.cible = 0; if (E.etat !== "vide") E.etat = "disparition"; },
    animer(dt, tS) {
      E.apparition += (E.cible - E.apparition) * Math.min(1, dt * (E.cible ? 3.2 : 6.5));
      if (E.cible === 0 && E.apparition < 0.02) { groupe.visible = false; E.apparition = 0; E.etat = E.maille ? "cache" : "vide"; }
      if (!groupe.visible) return;
      if (E.cible === 1 && E.impression < 1) {
        E.impression = Math.min(1, E.impression + dt / 1.6);   // 1,6 s pour « imprimer » l'objet de bas en haut
        if (E.impression >= 1) E.etat = "affiche";
      }
      uniformes.uImpression.value = E.cible === 1 ? E.impression : 1;
      uniformes.uApparition.value = E.apparition;
      E.rotation += dt * E.vitesse;
      groupe.rotation.y = E.rotation;
      groupe.scale.setScalar(E.echelleBase * E.echelleGeste);
      groupe.position.x = E.glissementX;
      groupe.position.y = E.baseY + E.glissementY + Math.sin(tS * 0.7) * 0.03;
      socle.material.color.copy(U.uCouleur.value);
      socle.material.opacity = E.apparition * (0.5 + 0.25 * Math.sin(tS * 2.0));
      socle.rotation.z += dt * 0.2;
    },
  };
}
