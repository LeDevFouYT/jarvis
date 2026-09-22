// Le réacteur en 3D (three.js local, hud/vendor) : cœur déformé par la voix, anneaux segmentés, bobines,
// gyroscopes, table holographique et son cône de projection, poussière de fond. Une seule boucle d'images,
// partagée avec le reste du HUD (surImage). Aucun post-traitement : tout l'éclat vient du mélange additif,
// ce qui tient 60 images/s en 2560×1440 même quand Ollama occupe la mémoire vidéo.
import * as THREE from "three";
import { THEMES, THEME_DEFAUT } from "./themes.js";
import { creerVisage } from "./visage.js";
import { creerHologramme } from "./hologramme.js";
import { creerGlobe } from "./globe.js";

// taille du réacteur dans la scène : son anneau extérieur fait environ le quart de la hauteur de l'écran
const TAILLE = 0.78, TAILLE_TABLE = 0.6;

const CYAN = new THREE.Color(0x5fe3ff), AMBRE = new THREE.Color(0xffb454);

// l'armure en cours : couleurs cibles du réacteur, lues à chaque image (aucune allocation)
const T = { nom: THEME_DEFAUT, principal: new THREE.Color(), accent: new THREE.Color(), erreur: new THREE.Color(),
  fond: new THREE.Vector3(), grille: new THREE.Vector3(), accentRepos: 0 };
function chargerTheme(nom) {
  const t = THEMES[nom] || THEMES[THEME_DEFAUT];
  T.nom = THEMES[nom] ? nom : THEME_DEFAUT;
  T.principal.set(t.principal); T.accent.set(t.accent); T.erreur.set(t.erreur);
  T.fond.set(...t.fond); T.grille.set(...t.grille); T.accentRepos = t.accentRepos;
}
chargerTheme(THEME_DEFAUT);

// La transition d'armure (le réacteur « recharge ») : il s'éteint (0 à 0,45 s), change de couleur dans le noir,
// puis se rallume en surcharge avec une onde de choc et les bobines en chenillard, et se stabilise vers 1,8 s.
const RECHARGE = { extinction: 0.45, surcharge: 0.95, fin: 1.8 };
// réglages par état : vitesse de rotation, agitation du cœur, intensité, tourbillon et aspiration des particules
const ETATS = {
  repos:     { vitesse: 0.22, agitation: 0.0, intensite: 0.38, tourbillon: 0.10, aspiration: 0.0, accent: 0.0 },
  ecoute:    { vitesse: 0.45, agitation: 0.2, intensite: 0.62, tourbillon: 0.25, aspiration: 1.0, accent: 0.0 },
  reflexion: { vitesse: 2.10, agitation: 1.0, intensite: 0.62, tourbillon: 1.00, aspiration: 0.3, accent: 1.0 },
  parole:    { vitesse: 0.70, agitation: 0.3, intensite: 0.46, tourbillon: 0.35, aspiration: 0.0, accent: 0.0 },
  erreur:    { vitesse: 0.30, agitation: 0.6, intensite: 0.55, tourbillon: 0.20, aspiration: 0.0, accent: 0.0, erreur: true },
};

// bruit de simplex 3D (Ashima Arts, domaine public, MIT) : déformation du cœur
const BRUIT = `
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+10.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z); vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
  vec4 m=max(0.5-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
  return 105.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}`;

function additif(uniforms, vertexShader, fragmentShader, extra = {}) {
  return new THREE.ShaderMaterial({ uniforms, vertexShader, fragmentShader, transparent: true, depthWrite: false,
    blending: THREE.AdditiveBlending, side: THREE.DoubleSide, ...extra });
}

function textureHalo() {
  const c = document.createElement("canvas"); c.width = c.height = 256;
  const g = c.getContext("2d"), d = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  d.addColorStop(0, "rgba(255,255,255,1)"); d.addColorStop(0.18, "rgba(255,255,255,.55)");
  d.addColorStop(0.45, "rgba(255,255,255,.14)"); d.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = d; g.fillRect(0, 0, 256, 256);
  return new THREE.CanvasTexture(c);
}

export function creerReacteur(canvas) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  } catch (e) {
    return null;                                     // pas de WebGL : le HUD passe en réacteur CSS
  }
  const plafondResolution = 1.25;                   // au-delà, l'œil ne voit rien et la carte paie
  let resolution = Math.min(devicePixelRatio || 1, plafondResolution);
  renderer.setPixelRatio(resolution);
  renderer.setClearColor(0x000000, 1);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(34, innerWidth / innerHeight, 0.1, 200);
  camera.position.set(0, 1.7, 12.5);
  camera.lookAt(0, 0.1, 0);

  // uniformes partagés : changer la couleur ici la change partout
  const U = {
    uTemps: { value: 0 }, uCouleur: { value: CYAN.clone() }, uAccent: { value: AMBRE.clone() },
    uAccentForce: { value: 0 }, uIntensite: { value: 0.4 }, uNiveau: { value: 0 }, uAgitation: { value: 0 },
    uPixelRatio: { value: resolution }, uDiscret: { value: 0 },
    uPhaseBruit: { value: 0 },       // intégrée à chaque image : changer d'agitation ne fait pas sauter le cœur
  };

  // ---------------------------------------------------------------- fond : dégradé, grille de points, bande de balayage
  const fond = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShaderMaterial({
    uniforms: { uTemps: U.uTemps, uResolution: { value: new THREE.Vector2(innerWidth, innerHeight) }, uDiscret: U.uDiscret,
      uFond: { value: new THREE.Vector3(...THEMES[THEME_DEFAUT].fond) }, uGrille: { value: new THREE.Vector3(...THEMES[THEME_DEFAUT].grille) } },
    depthWrite: false, depthTest: false,
    vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`,
    fragmentShader: `
      uniform float uTemps; uniform vec2 uResolution; uniform float uDiscret; uniform vec3 uFond; uniform vec3 uGrille; varying vec2 vUv;
      void main(){
        vec2 p = vUv - 0.5; p.x *= uResolution.x / uResolution.y;
        float r = length(p);
        vec3 c = mix(uFond, vec3(0.0), smoothstep(0.0, 1.05, r));
        vec2 g = fract(gl_FragCoord.xy / 46.0) - 0.5;
        float point = smoothstep(0.06, 0.0, length(g)) * (1.0 - smoothstep(0.2, 1.0, r));
        c += uGrille * point * 0.10 * (1.0 - uDiscret * 0.7);
        float bande = smoothstep(0.012, 0.0, abs(fract(vUv.y - uTemps * 0.045) - 0.5)) * 0.035;
        c += uGrille * bande * (1.0 - uDiscret);
        gl_FragColor = vec4(c, 1.0);
      }`,
  }));
  fond.frustumCulled = false; fond.renderOrder = -10;
  scene.add(fond);

  // ---------------------------------------------------------------- poussière de fond
  const NB = 2200, pos = new Float32Array(NB * 3), graine = new Float32Array(NB);
  for (let i = 0; i < NB; i++) {
    const r = 3 + Math.pow(Math.random(), 0.7) * 16, t = Math.random() * Math.PI * 2, f = Math.acos(2 * Math.random() - 1);
    pos[i * 3] = r * Math.sin(f) * Math.cos(t); pos[i * 3 + 1] = r * Math.cos(f) * 0.55; pos[i * 3 + 2] = r * Math.sin(f) * Math.sin(t) - 4;
    graine[i] = Math.random();
  }
  const gPoussiere = new THREE.BufferGeometry();
  gPoussiere.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  gPoussiere.setAttribute("aGraine", new THREE.BufferAttribute(graine, 1));
  const uPoussiere = { uTemps: U.uTemps, uCouleur: U.uCouleur, uPixelRatio: U.uPixelRatio, uDiscret: U.uDiscret,
    uTourbillon: { value: 0.1 }, uAspiration: { value: 0 }, uAngle: { value: 0 } };
  const poussiere = new THREE.Points(gPoussiere, additif(uPoussiere, `
      uniform float uTemps; uniform float uPixelRatio; uniform float uTourbillon; uniform float uAspiration; uniform float uAngle;
      attribute float aGraine; varying float vAlpha;
      void main(){
        vec3 p = position;
        float a = uAngle * (0.4 + aGraine);
        float c = cos(a), s = sin(a);
        p.xz = mat2(c, -s, s, c) * p.xz;
        p.y += sin(uTemps * 0.25 + aGraine * 31.0) * 0.18;
        p *= 1.0 - uAspiration * 0.22 * smoothstep(9.0, 3.0, length(position.xz));
        vec4 mv = modelViewMatrix * vec4(p, 1.0);
        gl_PointSize = uPixelRatio * (1.2 + aGraine * 2.4) * (14.0 / -mv.z);
        vAlpha = (0.25 + 0.75 * abs(sin(uTemps * (0.4 + aGraine) + aGraine * 50.0))) * smoothstep(34.0, 9.0, -mv.z);
        gl_Position = projectionMatrix * mv;
      }`, `
      uniform vec3 uCouleur; uniform float uDiscret; varying float vAlpha;
      void main(){
        float d = length(gl_PointCoord - 0.5);
        gl_FragColor = vec4(uCouleur, smoothstep(0.5, 0.0, d) * vAlpha * 0.55 * (1.0 - uDiscret * 0.85));
      }`));
  poussiere.frustumCulled = false;
  scene.add(poussiere);

  // ---------------------------------------------------------------- table holographique et cône de projection
  const table = new THREE.Group();
  table.position.y = -2.3;
  table.scale.setScalar(TAILLE_TABLE);
  scene.add(table);
  const uTable = { uTemps: U.uTemps, uCouleur: U.uCouleur, uOpacite: { value: 1 } };
  const disque = new THREE.Mesh(new THREE.PlaneGeometry(10, 10), additif(uTable, `
      varying vec2 vP; void main(){ vP = position.xy; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`, `
      uniform float uTemps; uniform vec3 uCouleur; uniform float uOpacite; varying vec2 vP;
      float cercle(float r, float R, float e){ return smoothstep(e, 0.0, abs(r - R)); }
      void main(){
        float r = length(vP);
        if (r > 4.7) discard;
        float a = atan(vP.y, vP.x) / 6.2831853 + 0.5;
        float traits = cercle(r, 4.3, 0.028) + cercle(r, 3.55, 0.012) * 0.7 + cercle(r, 2.6, 0.02) * 0.6 + cercle(r, 1.55, 0.012) * 0.5;
        float gradu = step(0.82, fract(a * 144.0)) * smoothstep(0.16, 0.0, abs(r - 4.05));
        float grandes = step(0.9, fract(a * 12.0)) * smoothstep(0.34, 0.0, abs(r - 3.9));
        float rayons = smoothstep(0.004, 0.0, abs(fract(a * 24.0) - 0.5) / 24.0 * r) * smoothstep(4.3, 1.6, r) * 0.25;
        float s = fract(a - uTemps * 0.07);
        float balayage = pow(s, 10.0) * smoothstep(4.3, 0.4, r) * 0.9;
        float centre = smoothstep(2.2, 0.0, r) * 0.18;
        float alpha = (traits * 0.55 + gradu * 0.45 + grandes * 0.5 + rayons + balayage * 0.35 + centre) * smoothstep(4.7, 4.1, r);
        gl_FragColor = vec4(uCouleur, alpha * uOpacite * 0.8);
      }`));
  disque.rotation.x = -Math.PI / 2;
  table.add(disque);
  const cone = new THREE.Mesh(new THREE.CylinderGeometry(1.35, 3.2, 2.35, 72, 1, true), additif({ ...uTable }, `
      varying float vY; varying float vBord;
      void main(){
        vY = uv.y;
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vBord = 1.0 - abs(dot(normalize(normalMatrix * normal), normalize(-mv.xyz)));
        gl_Position = projectionMatrix * mv;
      }`, `
      uniform float uTemps; uniform vec3 uCouleur; uniform float uOpacite; varying float vY; varying float vBord;
      void main(){
        float bandes = 0.65 + 0.35 * sin(vY * 46.0 - uTemps * 3.2);
        float a = pow(1.0 - vY, 1.6) * (0.05 + pow(vBord, 3.0) * 0.16) * bandes;
        gl_FragColor = vec4(uCouleur, a * uOpacite);
      }`));
  cone.position.y = 1.18;
  table.add(cone);

  // ---------------------------------------------------------------- le réacteur
  const reacteur = new THREE.Group();
  reacteur.position.y = 0.45;
  scene.add(reacteur);
  const pivot = new THREE.Group();                  // le balancement lent, qui montre la profondeur
  reacteur.add(pivot);

  // le cœur
  const coeur = new THREE.Mesh(new THREE.IcosahedronGeometry(0.66, 6), new THREE.ShaderMaterial({
    uniforms: { uTemps: U.uTemps, uNiveau: U.uNiveau, uAgitation: U.uAgitation, uCouleur: U.uCouleur, uIntensite: U.uIntensite, uPhaseBruit: U.uPhaseBruit },
    vertexShader: BRUIT + `
      uniform float uTemps; uniform float uNiveau; uniform float uAgitation; uniform float uPhaseBruit;
      varying vec3 vNormale; varying vec3 vVue; varying float vBruit;
      void main(){
        float n = snoise(normal * 2.1 + vec3(uPhaseBruit));
        vec3 p = position + normal * n * (0.028 + uNiveau * 0.2 + uAgitation * 0.05);
        vBruit = n;
        vec4 mv = modelViewMatrix * vec4(p, 1.0);
        vNormale = normalize(normalMatrix * normal); vVue = normalize(-mv.xyz);
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: `
      uniform vec3 uCouleur; uniform float uIntensite; varying vec3 vNormale; varying vec3 vVue; varying float vBruit;
      void main(){
        float face = max(dot(vNormale, vVue), 0.0);
        float bord = pow(1.0 - face, 2.4);
        vec3 c = mix(uCouleur * 0.7, vec3(1.0), pow(face, 2.6) * 0.9) + uCouleur * bord * 1.6;
        c *= 0.6 + min(uIntensite, 1.1) * 0.55 + vBruit * 0.07;
        gl_FragColor = vec4(c, 1.0);
      }`,
  }));
  pivot.add(coeur);

  const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: textureHalo(), color: CYAN.clone(), blending: THREE.AdditiveBlending,
    transparent: true, depthWrite: false }));
  halo.scale.setScalar(4.2);
  pivot.add(halo);

  // anneaux segmentés, dans le plan face à la caméra
  const anneaux = [];
  function anneau(interieur, exterieur, segments, remplissage, vitesse, opacite, accent = 0) {
    const u = { uCouleur: U.uCouleur, uAccent: U.uAccent, uAccentForce: U.uAccentForce, uOpacite: { value: opacite },
      uSegments: { value: segments }, uRemplissage: { value: remplissage }, uInt: { value: interieur }, uExt: { value: exterieur },
      uEstAccent: { value: accent }, uIntensite: U.uIntensite };
    const m = new THREE.Mesh(new THREE.RingGeometry(interieur, exterieur, 256, 1), additif(u, `
        varying vec2 vP; void main(){ vP = position.xy; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`, `
        uniform vec3 uCouleur; uniform vec3 uAccent; uniform float uAccentForce; uniform float uEstAccent; uniform float uOpacite;
        uniform float uSegments; uniform float uRemplissage; uniform float uInt; uniform float uExt; uniform float uIntensite;
        varying vec2 vP;
        void main(){
          float r = length(vP);
          float a = atan(vP.y, vP.x) / 6.2831853 + 0.5;
          float motif = 1.0;
          if (uSegments > 0.5) {
            float f = fract(a * uSegments);
            float w = uSegments * fwidth(r) / max(r * 6.2831853, 0.001) * 1.5;
            motif = smoothstep(0.0, w, f) * smoothstep(uRemplissage + w, uRemplissage, f);
          }
          float e = (uExt - uInt) * 0.3;
          float bord = smoothstep(uInt, uInt + e, r) * (1.0 - smoothstep(uExt - e, uExt, r));
          vec3 c = mix(uCouleur, uAccent, uEstAccent * uAccentForce);
          gl_FragColor = vec4(c, motif * bord * uOpacite * (0.65 + uIntensite * 0.6));
        }`));
    m.userData.vitesse = vitesse;
    pivot.add(m); anneaux.push(m);
    return m;
  }
  anneau(0.84, 0.88, 0, 1, 0, 0.55);
  anneau(1.42, 1.54, 36, 0.62, 0.35, 0.8, 1);
  anneau(1.68, 1.72, 144, 0.28, -0.22, 0.75);
  anneau(1.98, 2.1, 6, 0.72, 0.5, 0.6, 1);
  anneau(2.36, 2.38, 3, 0.94, -0.12, 0.7);
  anneau(2.52, 2.54, 240, 0.18, 0.06, 0.45);

  // les bobines autour du cœur, qui s'allument en chenillard pendant la réflexion
  const NB_BOBINES = 12;
  const bobines = new THREE.InstancedMesh(new THREE.BoxGeometry(0.2, 0.36, 0.06),
    new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending, depthWrite: false }), NB_BOBINES);
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), v3 = new THREE.Vector3(), un = new THREE.Vector3(1, 1, 1), axeZ = new THREE.Vector3(0, 0, 1);
  const echelleBarre = new THREE.Vector3(1, 1, 1), couleurBobine = new THREE.Color();   // réutilisés : aucune allocation par image
  for (let i = 0; i < NB_BOBINES; i++) {
    const a = (i / NB_BOBINES) * Math.PI * 2;
    q.setFromAxisAngle(axeZ, a - Math.PI / 2);
    bobines.setMatrixAt(i, m4.compose(v3.set(Math.cos(a) * 1.14, Math.sin(a) * 1.14, 0), q, un));
    bobines.setColorAt(i, CYAN);
  }
  pivot.add(bobines);

  // barres du micro, en couronne, pendant l'écoute
  const NB_BARRES = 84;
  const gBarre = new THREE.PlaneGeometry(0.034, 1); gBarre.translate(0, 0.5, 0);
  const barres = new THREE.InstancedMesh(gBarre, new THREE.MeshBasicMaterial({ color: CYAN, transparent: true, opacity: 0,
    blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }), NB_BARRES);
  pivot.add(barres);

  // ondes de parole
  const ondes = [0, 1, 2].map(() => {
    const m = new THREE.Mesh(new THREE.RingGeometry(0.97, 1.0, 180, 1), new THREE.MeshBasicMaterial({ color: CYAN, transparent: true,
      opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
    pivot.add(m); return m;
  });

  // gyroscopes inclinés et leurs satellites
  const gyros = [[1.15, 0.0, 0.35], [-0.95, 0.6, -0.22]].map(([rx, ry, vitesse]) => {
    const g = new THREE.Group(); g.rotation.set(rx, ry, 0);
    const t = new THREE.Mesh(new THREE.TorusGeometry(2.9, 0.008, 6, 256), new THREE.MeshBasicMaterial({ color: CYAN, transparent: true,
      opacity: 0.32, blending: THREE.AdditiveBlending, depthWrite: false }));
    const sat = new THREE.Mesh(new THREE.IcosahedronGeometry(0.055, 2), new THREE.MeshBasicMaterial({ color: 0xffffff }));
    const lueur = new THREE.Sprite(new THREE.SpriteMaterial({ map: halo.material.map, color: CYAN.clone(), blending: THREE.AdditiveBlending,
      transparent: true, depthWrite: false }));
    lueur.scale.setScalar(0.5); sat.add(lueur);
    g.add(t, sat); reacteur.add(g);
    return { g, sat, lueur, vitesse, angle: Math.random() * 6 };
  });

  // ---------------------------------------------------------------- l'anneau de la conversation continue
  // Après une réponse, Jarvis écoute quelques secondes sans mot de réveil : un arc lumineux se vide pendant ce temps.
  const uDecompte = { uCouleur: U.uCouleur, uReste: { value: 0 }, uOpacite: { value: 0 } };
  const decompte = new THREE.Mesh(new THREE.RingGeometry(2.66, 2.74, 256, 1), additif(uDecompte, `
      varying vec2 vP; void main(){ vP = position.xy; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`, `
      uniform vec3 uCouleur; uniform float uReste; uniform float uOpacite; varying vec2 vP;
      void main(){
        float a = fract(0.25 - atan(vP.y, vP.x) / 6.2831853);      // part du haut, tourne dans le sens des aiguilles
        float plein = step(a, uReste);
        float r = length(vP);
        float bord = smoothstep(2.66, 2.69, r) * (1.0 - smoothstep(2.71, 2.74, r));
        vec3 c = mix(uCouleur, vec3(1.0), 0.35);
        gl_FragColor = vec4(c, (plein * 0.95 + 0.12) * bord * uOpacite);
      }`));
  pivot.add(decompte);
  const D = { debut: 0, duree: 0, actif: false };

  // le visage de particules, dans le même repère que les anneaux d'où il naît
  const visage = creerVisage(U);
  reacteur.add(visage.objet);

  // l'hologramme : devant le réacteur, posé au-dessus de la table (consigne 4)
  const hologramme = creerHologramme(U);
  hologramme.placer(0, -0.55, 2.2, 2.3);
  scene.add(hologramme.objet);

  // le globe (consigne 7) : à la même place que l'hologramme, mais posé sur son centre
  const globe = creerGlobe(U);
  globe.placer(0, 0.5, 2.2, 1.35);
  scene.add(globe.objet);

  // ---------------------------------------------------------------- état, cibles et boucle
  const S = { etat: "repos", niveau: 0, niveauCible: 0, micro: 0, microCible: 0, vitesse: 0.22, aspiration: 0, tourbillon: 0.1,
    recul: 0, decalage: 0, decalageCible: 0, rayonMax: 0, echelle: 1, discret: 0, discretCible: 0, erreurJusqua: 0, avant: "repos" };
  const couleurCible = CYAN.clone();
  const R = { actif: false, debut: 0, bascule: false, suivant: THEME_DEFAUT, facteur: 1, elan: 1 };
  const surBascule = [];
  function basculerCouleurs(instantane = false) {    // au creux de l'extinction : la nouvelle armure, d'un coup
    chargerTheme(R.suivant);
    U.uCouleur.value.copy(T.principal); U.uAccent.value.copy(T.accent);
    fond.material.uniforms.uFond.value.copy(T.fond); fond.material.uniforms.uGrille.value.copy(T.grille);
    R.bascule = true;
    surBascule.forEach(f => f(T.nom, instantane));
  }
  const rappels = [];
  const temps = new Float32Array(600); let indexTemps = 0, images = 0;
  let dernier = performance.now(), debut = dernier, sauter = false, lentes = 0;

  function redimensionner() {
    const w = innerWidth, h = innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    fond.material.uniforms.uResolution.value.set(w * resolution, h * resolution);
    appliquerCadrage();
  }
  function appliquerCadrage() {
    const w = innerWidth, h = innerHeight, d = S.discret;
    // setViewOffset décale la fenêtre de vue : un décalage positif fait glisser l'image vers la gauche (x) ou le haut (y).
    // Panneaux ouverts : le réacteur glisse à gauche. Mode discret : il part dans le coin bas droit.
    const dx = S.decalage * (1 - d) - d * (w / 2 - Math.min(w, h) * 0.16);
    const dy = -d * (h / 2 - Math.min(w, h) * 0.17);
    camera.setViewOffset(w, h, dx, dy, w, h);
    camera.updateProjectionMatrix();
  }
  addEventListener("resize", redimensionner);
  redimensionner();

  function image(t) {
    requestAnimationFrame(image);
    const dt = Math.min(0.05, (t - dernier) / 1000);
    temps[indexTemps++ % temps.length] = t - dernier; images++;
    dernier = t;
    // mode discret : une image sur deux suffit (30 i/s), la carte reste aux jeux
    if (S.discret > 0.99) { sauter = !sauter; if (sauter) { rappels.forEach(f => f(dt, t)); return; } }

    if (S.etat === "erreur" && t > S.erreurJusqua) definirEtat(S.avant === "erreur" ? "repos" : S.avant);
    const cible = ETATS[S.etat] || ETATS.repos;
    const k = 1 - Math.pow(0.02, dt);                 // lissage indépendant de la cadence
    S.niveau += (S.niveauCible - S.niveau) * (S.niveauCible > S.niveau ? 0.55 : 0.18);
    S.micro += (S.microCible - S.micro) * 0.35;
    S.vitesse += (cible.vitesse - S.vitesse) * k;
    S.tourbillon += (cible.tourbillon - S.tourbillon) * k;
    S.aspiration += (cible.aspiration - S.aspiration) * k;
    S.decalage += (S.decalageCible - S.decalage) * k * 0.8;
    S.discret += (S.discretCible - S.discret) * k * 0.8;
    const erreur = S.etat === "erreur";
    couleurCible.copy(erreur ? T.erreur : T.principal);
    U.uCouleur.value.lerp(couleurCible, k);
    U.uAccent.value.lerp(T.accent, k);
    U.uAccentForce.value += (Math.max(cible.accent, T.accentRepos) - U.uAccentForce.value) * k;
    fond.material.uniforms.uFond.value.lerp(T.fond, k); fond.material.uniforms.uGrille.value.lerp(T.grille, k);
    // la recharge : extinction, bascule des couleurs dans le noir, surcharge, retour au calme
    R.facteur = 1; R.elan = 1;
    if (R.actif) {
      const p = (t - R.debut) / 1000;
      if (p < RECHARGE.extinction) R.facteur = 1 - 0.9 * THREE.MathUtils.smootherstep(p, 0, RECHARGE.extinction);
      else {
        if (!R.bascule) basculerCouleurs();
        const montee = THREE.MathUtils.smootherstep(p, RECHARGE.extinction, RECHARGE.surcharge);
        const calme = THREE.MathUtils.smootherstep(p, RECHARGE.surcharge, RECHARGE.fin);
        R.facteur = 0.1 + montee * 1.9 - calme * 0.9;              // 0,1 -> 2,0 (surcharge) -> 1,0
        R.elan = 1 + montee * 5 * (1 - calme);                     // les anneaux s'emballent puis ralentissent
        if (p >= RECHARGE.fin) R.actif = false;
      }
    }
    U.uAgitation.value += (cible.agitation - U.uAgitation.value) * k;
    U.uNiveau.value = S.niveau;
    U.uDiscret.value = S.discret;
    const tS = (t - debut) / 1000;
    U.uTemps.value = tS;
    const souffle = 0.5 + 0.5 * Math.sin(tS * 1.5);
    let intensite = cible.intensite + (S.etat === "repos" ? souffle * 0.12 : 0) + S.niveau * 0.4 + S.micro * 0.35;
    if (S.etat === "reflexion") intensite += 0.14 * Math.sin(tS * 9);
    if (erreur) intensite *= 0.75 + 0.25 * Math.round(Math.random());
    // le visage (« montre-toi ») : le réacteur s'éteint pendant que ses particules quittent les anneaux ;
    // un hologramme affiché devant lui le fait passer au second plan
    hologramme.animer(dt, tS);
    globe.animer(dt, tS);
    // un hologramme devant lui : le réacteur recule et rapetisse, il devient le projecteur de la scène
    S.recul += ((hologramme.visible || globe.visible ? 1 : 0) - S.recul) * k * 0.7;
    const fv = visage.forme;
    const eteint = (fv < 0.35 ? 1 - (fv / 0.35) * 0.9 : 1) * (1 - S.recul * 0.65);
    U.uIntensite.value += (intensite * R.facteur * eteint - U.uIntensite.value) * 0.35;
    uPoussiere.uTourbillon.value = S.tourbillon; uPoussiere.uAspiration.value = S.aspiration;
    uPoussiere.uAngle.value += dt * (0.015 + S.tourbillon * 0.09);
    U.uPhaseBruit.value += dt * (0.35 + U.uAgitation.value * 0.9 + S.niveau * 1.2);
    uTable.uOpacite.value = 1 - S.discret;

    // le réacteur
    // espace libre imposé par les panneaux : le réacteur rétrécit juste assez pour y tenir (anneau extérieur)
    let echelleCible = 1;
    if (S.rayonMax > 0) {
      const pxParUnite = innerHeight / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * camera.position.distanceTo(reacteur.position));
      echelleCible = Math.max(0.45, Math.min(1, S.rayonMax / (TAILLE * 2.62 * pxParUnite)));
    }
    S.echelle += (echelleCible - S.echelle) * k * 0.8;
    const echelle = (1 - S.discret * 0.62) * (1 - S.recul * 0.4) * S.echelle;
    reacteur.scale.setScalar(TAILLE * echelle);
    table.scale.setScalar(TAILLE_TABLE * echelle);
    reacteur.position.y = 0.45 + Math.sin(tS * 0.8) * 0.06 * (1 - S.discret) + S.recul * 0.5;
    reacteur.position.z = -S.recul * 3.4;
    table.position.z = -S.recul * 3.4;
    visage.animer(dt, tS, S.etat === "parole" ? S.niveau : S.niveau * 0.5);
    pivot.visible = fv < 0.35;
    pivot.scale.setScalar(1 + fv * 0.8);
    visage.objet.rotation.y = Math.sin(tS * 0.21) * 0.14;
    visage.objet.rotation.x = Math.sin(tS * 0.17) * 0.05;
    pivot.rotation.y = Math.sin(tS * 0.21) * 0.2;
    pivot.rotation.x = -0.1 + Math.sin(tS * 0.17) * 0.07;
    const battement = S.etat === "parole" ? 1 + S.niveau * 0.22 : S.etat === "ecoute" ? 0.93 + S.micro * 0.1 : 1 + souffle * 0.03;
    coeur.scale.setScalar(battement);
    halo.scale.setScalar(3.2 + U.uIntensite.value * 1.8 + S.niveau * 1.1);
    halo.material.color.copy(U.uCouleur.value);
    halo.material.opacity = Math.min(0.85, 0.45 + U.uIntensite.value * 0.28);
    for (const a of anneaux) a.rotation.z += a.userData.vitesse * S.vitesse * dt * (S.etat === "reflexion" ? 1.6 : 1) * R.elan;
    anneaux[1].scale.setScalar(1 + S.aspiration * 0.05 + S.micro * 0.04);

    for (let i = 0; i < NB_BOBINES; i++) {
      let lum = 0.45 + U.uIntensite.value * 0.4;
      if (S.etat === "reflexion" || R.actif) lum = 0.25 + Math.pow(Math.max(0, Math.cos((i / NB_BOBINES) * Math.PI * 2 - tS * (R.actif ? 14 : 6))), 6) * 1.2;
      lum *= R.facteur;
      if (S.etat === "parole") lum += S.niveau * 0.8;
      bobines.setColorAt(i, couleurBobine.setRGB(U.uCouleur.value.r * lum, U.uCouleur.value.g * lum, U.uCouleur.value.b * lum));
    }
    bobines.instanceColor.needsUpdate = true;
    bobines.rotation.z -= S.vitesse * dt * 0.4;

    const microVisible = Math.max(S.aspiration, S.micro);
    barres.material.opacity = microVisible * 0.85;
    barres.visible = microVisible > 0.01;
    if (barres.visible) {
      for (let i = 0; i < NB_BARRES; i++) {
        const a = (i / NB_BARRES) * Math.PI * 2;
        const h = 0.04 + S.micro * (0.18 + 0.32 * Math.abs(Math.sin(i * 1.93 + tS * 7.3) * Math.sin(i * 0.61 - tS * 3.1)));
        q.setFromAxisAngle(axeZ, a - Math.PI / 2);
        barres.setMatrixAt(i, m4.compose(v3.set(Math.cos(a) * 2.2, Math.sin(a) * 2.2, 0), q, echelleBarre.set(1, h, 1)));
      }
      barres.instanceMatrix.needsUpdate = true;
      barres.material.color.copy(U.uCouleur.value);
    }

    ondes.forEach((o, i) => {
      const phase = (tS * 0.9 + i / 3) % 1;
      o.scale.setScalar(0.95 + phase * 1.7);
      o.material.opacity = S.etat === "parole" ? (1 - phase) * S.niveau * 0.7 : 0;
      if (R.actif && R.bascule) {                     // l'onde de choc de la recharge, les trois anneaux décalés
        const q = Math.min(1, ((t - R.debut) / 1000 - RECHARGE.extinction) / 0.9 - i * 0.12);
        if (q > 0 && q < 1) { o.scale.setScalar(0.9 + q * 2.6); o.material.opacity = (1 - q) * 0.9; }
      }
      o.material.color.copy(U.uCouleur.value);
    });

    for (const g of gyros) {
      g.g.rotation.z += g.vitesse * S.vitesse * dt * 2;
      g.angle += dt * (0.5 + S.vitesse * 0.6);
      g.sat.position.set(Math.cos(g.angle) * 2.9, Math.sin(g.angle) * 2.9, 0);
      g.lueur.material.color.copy(U.uCouleur.value);
      g.g.children[0].material.color.copy(U.uCouleur.value);
    }

    // l'anneau de la conversation continue : plein au début de la fenêtre, vide à sa fin
    const resteFenetre = D.actif ? Math.max(0, 1 - (t - D.debut) / D.duree) : 0;
    if (D.actif && resteFenetre <= 0) D.actif = false;
    uDecompte.uReste.value = resteFenetre;
    uDecompte.uOpacite.value += ((D.actif ? 1 : 0) - uDecompte.uOpacite.value) * 0.15;
    decompte.visible = uDecompte.uOpacite.value > 0.01;

    appliquerCadrage();
    rappels.forEach(f => f(dt, t));
    renderer.render(scene, camera);

    // filet de sécurité : si la machine n'arrive plus à suivre, on baisse la définition plutôt que la cadence
    if (images % 120 === 0 && !S.discretCible) {
      let somme = 0; for (let i = 1; i <= 120; i++) somme += temps[(indexTemps - i + temps.length) % temps.length];
      lentes = somme / 120 > 19 ? lentes + 1 : 0;
      if (lentes >= 3 && resolution > 0.6) {
        resolution = Math.max(0.6, resolution - 0.1); renderer.setPixelRatio(resolution); U.uPixelRatio.value = resolution; redimensionner(); lentes = 0;
      }
    }
  }
  requestAnimationFrame(image);

  function definirEtat(nom) {
    if (nom === "erreur") { S.avant = S.etat === "erreur" ? S.avant : S.etat; S.erreurJusqua = performance.now() + 1200; }
    S.etat = nom;
  }

  return {
    etat: definirEtat,
    get etatActuel() { return S.etat; },
    niveau(v) { S.niveauCible = Math.max(0, Math.min(1, v)); },
    micro(v) { S.microCible = Math.max(0, Math.min(1, v)); },
    erreurLongue() { S.erreurJusqua = performance.now() + 3600e3; },
    decaler(px, rayonMax = 0) { S.decalageCible = px; S.rayonMax = rayonMax; },
    discret(actif) { S.discretCible = actif ? 1 : 0; },
    // conversation continue : l'anneau se vide en `secondes` ; `finDecompte` l'éteint (parole reçue ou délai passé)
    decompte(secondes) { D.debut = performance.now(); D.duree = Math.max(0.5, secondes) * 1000; D.actif = true; },
    finDecompte() { D.actif = false; },
    surImage(f) { rappels.push(f); },
    // l'armure : `instantane` pour un chargement de page (pas d'animation), sinon le réacteur recharge
    theme(nom, instantane = false) {
      R.suivant = THEMES[nom] ? nom : THEME_DEFAUT;
      if (instantane) { R.actif = false; basculerCouleurs(true); return; }
      R.actif = true; R.debut = performance.now(); R.bascule = false;
    },
    get themeActuel() { return R.actif && !R.bascule ? R.suivant : T.nom; },
    get enRecharge() { return R.actif; },
    get couleurActuelle() { return "#" + U.uCouleur.value.getHexString(); },   // pour les tests
    surBascule(f) { surBascule.push(f); },
    // le visage : `visage(true)` transforme le réacteur en visage de particules, `visage(false)` le rend
    visage(actif) { visage.actif = !!actif; },
    get visageActif() { return visage.actif; },
    get formeVisage() { return visage.forme; },      // pour les tests : 0 réacteur, 1 visage
    // l'hologramme (consigne 4) : `hologramme(url, objet)` l'affiche, `cacherHologramme()` le retire
    hologramme(url, objet) { return hologramme.afficher(url, objet); },
    cacherHologramme() { hologramme.cacher(); },
    tournerHologramme(delta) { hologramme.tourner(delta); },
    echelleHologramme(e) { hologramme.echelle(e); },
    deplacerHologramme(dx, dy) { hologramme.deplacer(dx, dy); },
    get reglageHologramme() { return hologramme.reglageGeste; },
    // le globe (consigne 7)
    globe(quoi, donnees, avenir) {
      hologramme.cacher();                                   // un seul objet à la fois devant le réacteur
      if (quoi === "cacher") { globe.cacher(); return null; }
      if (quoi === "station") globe.placerStation(donnees, avenir);
      else if (quoi === "seismes") globe.placerSeismes(donnees);
      return globe.afficher();
    },
    get etatGlobe() { return globe.etat; },
    globeEcran(lat, lon) { return globe.ecran(lat, lon, camera); },
    get boiteHologramme() { return hologramme.boite; },
    get etatHologramme() { return { etat: hologramme.etat, objet: hologramme.objetAffiche, impression: hologramme.impression,
                                    visible: hologramme.visible, sommets: hologramme.sommets, rotation: hologramme.rotation }; },
    get boucheVisage() { return visage.bouche; },
    get clignement() { return visage.clignement; },
    get anneauxVisibles() { return pivot.visible; },
    // le point du réacteur sous le pointeur ? (maintenir pour parler)
    estSur(x, y) {
      const c = reacteur.getWorldPosition(new THREE.Vector3()).project(camera);
      const bord = reacteur.localToWorld(new THREE.Vector3(2.6, 0, 0)).project(camera);
      const cx = (c.x + 1) / 2 * innerWidth, cy = (1 - c.y) / 2 * innerHeight;
      const r = Math.abs((bord.x - c.x) / 2 * innerWidth);
      return Math.hypot(x - cx, y - cy) < r;
    },
    rayonEcran() {
      const c = reacteur.getWorldPosition(new THREE.Vector3()).project(camera);
      const bord = reacteur.localToWorld(new THREE.Vector3(2.55, 0, 0)).project(camera);
      return Math.abs((bord.x - c.x) / 2 * innerWidth);
    },
    centreEcran() {
      const c = reacteur.getWorldPosition(new THREE.Vector3()).project(camera);
      return { x: (c.x + 1) / 2 * innerWidth, y: (1 - c.y) / 2 * innerHeight };
    },
    // mesure de cadence : sur les `n` dernières images, ou sur une fenêtre de temps (mesurer)
    stats(n = 300) {
      const k = Math.min(n, images, temps.length), v = [];
      for (let i = 1; i <= k; i++) v.push(temps[(indexTemps - i + temps.length) % temps.length]);
      v.sort((a, b) => a - b);
      const moyenne = v.reduce((a, b) => a + b, 0) / Math.max(1, v.length);
      return { images: k, ips: Math.round(1000 / moyenne * 10) / 10, moyenne_ms: +moyenne.toFixed(2),
        p95_ms: +(v[Math.floor(v.length * 0.95)] || 0).toFixed(2), pire_ms: +(v[v.length - 1] || 0).toFixed(2),
        resolution, taille: [renderer.domElement.width, renderer.domElement.height], discret: S.discretCible === 1 };
    },
    mesurer(ms) {
      return new Promise(fin => {
        const v = []; let precedent = null; const stop = performance.now() + ms;
        (function boucle(t) {
          if (precedent !== null) v.push(t - precedent);
          precedent = t;
          if (t < stop) requestAnimationFrame(boucle);
          else {
            v.sort((a, b) => a - b);
            const moyenne = v.reduce((a, b) => a + b, 0) / v.length;
            fin({ images: v.length, duree_s: ms / 1000, ips: +(1000 / moyenne).toFixed(1), moyenne_ms: +moyenne.toFixed(2),
              p95_ms: +v[Math.floor(v.length * 0.95)].toFixed(2), p99_ms: +v[Math.floor(v.length * 0.99)].toFixed(2),
              pire_ms: +v[v.length - 1].toFixed(2), sous_60: v.filter(x => x > 1000 / 55).length,
              resolution, taille: [renderer.domElement.width, renderer.domElement.height] });
          }
        })(performance.now());
      });
    },
    carte() {
      const gl = renderer.getContext(), ext = gl.getExtension("WEBGL_debug_renderer_info");
      return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    },
  };
}
