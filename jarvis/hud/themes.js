// Les armures du HUD (v3, consigne 1) : chacune change le réacteur 3D (couleur, accent, fond), les panneaux (variables
// CSS), les particules (elles suivent la couleur du réacteur) et les sons d'interface. Une seule définition, lue par
// reacteur.js, hud.js et sons.js. Jarvis (cyan) reste l'armure par défaut.
//
// css : les variables de style.css. `--c`, `--a`… sont des canaux RGB (rgba(var(--c), .4)), les autres des couleurs.
// son : le timbre des bips (forme d'onde, note, filtre) ; `recharge` est le son de la transition d'armure.
export const THEMES = {
  jarvis: {
    libelle: "Jarvis", principal: 0x5fe3ff, accent: 0xffb454, erreur: 0xff4b4b, accentRepos: 0,
    fond: [0.027, 0.086, 0.15], grille: [0.37, 0.89, 1.0],
    css: { "--cyan": "#5fe3ff", "--cyan2": "#1a7d99", "--cyan3": "#0d3a4a", "--texte": "#cfeefa", "--dim": "#5d93a8", "--dim2": "#7fb3c6",
      "--ambre": "#ffb454", "--c": "95,227,255", "--c2rgb": "26,125,153", "--c3rgb": "13,58,74", "--a": "255,180,84",
      "--nuit": "2,12,22", "--nuit2": "8,38,58", "--clair": "#e6fbff", "--clair-rgb": "191,244,255", "--cyan-sombre": "#1d4a5c", "--fonce": "#06131d" },
    son: { forme: "sine", note: 1320, filtre: 6000, duree: 0.09 },
  },
  mark3: {
    // rouge et or : les cadres et le réacteur en rouge, les anneaux d'accent et les textes clairs en or
    libelle: "Mark III", principal: 0xff4234, accent: 0xffc23a, erreur: 0xffffff, accentRepos: 0.75,
    fond: [0.13, 0.03, 0.02], grille: [1.0, 0.76, 0.23],
    css: { "--cyan": "#ff4a3a", "--cyan2": "#9e2418", "--cyan3": "#46100b", "--texte": "#ffe9cf", "--dim": "#a8624f", "--dim2": "#d39a7e",
      "--ambre": "#ffc23a", "--c": "255,74,58", "--c2rgb": "158,36,24", "--c3rgb": "70,16,11", "--a": "255,194,58",
      "--nuit": "20,4,3", "--nuit2": "48,10,8", "--clair": "#ffe7b0", "--clair-rgb": "255,215,140", "--cyan-sombre": "#5a1a12", "--fonce": "#1a0605" },
    son: { forme: "square", note: 660, filtre: 1900, duree: 0.07 },
  },
  friday: {
    libelle: "Friday", principal: 0xb57bff, accent: 0xff7ad9, erreur: 0xff4b6b, accentRepos: 0.2,
    fond: [0.07, 0.03, 0.14], grille: [0.71, 0.48, 1.0],
    css: { "--cyan": "#b57bff", "--cyan2": "#6a3fb0", "--cyan3": "#2c1650", "--texte": "#efe3ff", "--dim": "#8b6fb0", "--dim2": "#b39ad6",
      "--ambre": "#ff7ad9", "--c": "181,123,255", "--c2rgb": "106,63,176", "--c3rgb": "44,22,80", "--a": "255,122,217",
      "--nuit": "10,4,22", "--nuit2": "30,14,56", "--clair": "#f4ebff", "--clair-rgb": "228,206,255", "--cyan-sombre": "#3d2566", "--fonce": "#0e0619" },
    son: { forme: "triangle", note: 1760, filtre: 5000, duree: 0.16 },
  },
  ultron: {
    libelle: "Ultron", principal: 0xe0162b, accent: 0xff6a3a, erreur: 0xffffff, accentRepos: 0,
    fond: [0.09, 0.0, 0.012], grille: [0.8, 0.02, 0.1],
    css: { "--cyan": "#e0162b", "--cyan2": "#8a0a16", "--cyan3": "#3a0308", "--texte": "#ffd9d9", "--dim": "#9a4a4f", "--dim2": "#c77c80",
      "--ambre": "#ff6a3a", "--c": "224,22,43", "--c2rgb": "138,10,22", "--c3rgb": "58,3,8", "--a": "255,106,58",
      "--nuit": "16,1,3", "--nuit2": "40,4,8", "--clair": "#ffe1e1", "--clair-rgb": "255,180,180", "--cyan-sombre": "#4a0a10", "--fonce": "#120203" },
    son: { forme: "sawtooth", note: 110, filtre: 900, duree: 0.18 },
  },
};

export const THEME_DEFAUT = "jarvis";

export function appliquerCss(nom) {
  const t = THEMES[nom] || THEMES[THEME_DEFAUT];
  const style = document.documentElement.style;
  for (const [variable, valeur] of Object.entries(t.css)) style.setProperty(variable, valeur);
  document.documentElement.dataset.theme = nom;
}
