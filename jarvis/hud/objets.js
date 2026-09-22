// Les noms des objets que le modèle sait reconnaître (v3, consigne 6). EfficientDet-Lite0 est entraîné sur COCO :
// 80 catégories, nommées en anglais. Ici, leur nom en français, avec l'article, au singulier et au pluriel.
// Ce fichier est du texte pur : le test s'en sert pour vérifier qu'aucune catégorie ne sort en anglais.
export const NOMS = {
  person: ["une personne", "personnes"], bicycle: ["un vélo", "vélos"], car: ["une voiture", "voitures"],
  motorcycle: ["une moto", "motos"], airplane: ["un avion", "avions"], bus: ["un bus", "bus"],
  train: ["un train", "trains"], truck: ["un camion", "camions"], boat: ["un bateau", "bateaux"],
  "traffic light": ["un feu tricolore", "feux tricolores"], "fire hydrant": ["une bouche d'incendie", "bouches d'incendie"],
  "stop sign": ["un panneau stop", "panneaux stop"], "parking meter": ["un parcmètre", "parcmètres"],
  bench: ["un banc", "bancs"], bird: ["un oiseau", "oiseaux"], cat: ["un chat", "chats"], dog: ["un chien", "chiens"],
  horse: ["un cheval", "chevaux"], sheep: ["un mouton", "moutons"], cow: ["une vache", "vaches"],
  elephant: ["un éléphant", "éléphants"], bear: ["un ours", "ours"], zebra: ["un zèbre", "zèbres"],
  giraffe: ["une girafe", "girafes"], backpack: ["un sac à dos", "sacs à dos"], umbrella: ["un parapluie", "parapluies"],
  handbag: ["un sac à main", "sacs à main"], tie: ["une cravate", "cravates"], suitcase: ["une valise", "valises"],
  frisbee: ["un frisbee", "frisbees"], skis: ["des skis", "paires de skis"], snowboard: ["un snowboard", "snowboards"],
  "sports ball": ["un ballon", "ballons"], kite: ["un cerf-volant", "cerfs-volants"],
  "baseball bat": ["une batte", "battes"], "baseball glove": ["un gant de baseball", "gants de baseball"],
  skateboard: ["un skateboard", "skateboards"], surfboard: ["une planche de surf", "planches de surf"],
  "tennis racket": ["une raquette", "raquettes"], bottle: ["une bouteille", "bouteilles"],
  "wine glass": ["un verre à pied", "verres à pied"], cup: ["une tasse", "tasses"], fork: ["une fourchette", "fourchettes"],
  knife: ["un couteau", "couteaux"], spoon: ["une cuillère", "cuillères"], bowl: ["un bol", "bols"],
  banana: ["une banane", "bananes"], apple: ["une pomme", "pommes"], sandwich: ["un sandwich", "sandwichs"],
  orange: ["une orange", "oranges"], broccoli: ["un brocoli", "brocolis"], carrot: ["une carotte", "carottes"],
  "hot dog": ["un hot-dog", "hot-dogs"], pizza: ["une pizza", "pizzas"], donut: ["un beignet", "beignets"],
  cake: ["un gâteau", "gâteaux"], chair: ["une chaise", "chaises"], couch: ["un canapé", "canapés"],
  "potted plant": ["une plante", "plantes"], bed: ["un lit", "lits"], "dining table": ["une table", "tables"],
  toilet: ["des toilettes", "toilettes"], tv: ["un écran", "écrans"], laptop: ["un ordinateur portable", "ordinateurs portables"],
  mouse: ["une souris", "souris"], remote: ["une télécommande", "télécommandes"], keyboard: ["un clavier", "claviers"],
  "cell phone": ["un téléphone", "téléphones"], microwave: ["un micro-ondes", "micro-ondes"], oven: ["un four", "fours"],
  toaster: ["un grille-pain", "grille-pain"], sink: ["un évier", "éviers"], refrigerator: ["un réfrigérateur", "réfrigérateurs"],
  book: ["un livre", "livres"], clock: ["une horloge", "horloges"], vase: ["un vase", "vases"],
  scissors: ["des ciseaux", "paires de ciseaux"], "teddy bear": ["une peluche", "peluches"],
  "hair drier": ["un sèche-cheveux", "sèche-cheveux"], toothbrush: ["une brosse à dents", "brosses à dents"],
};

/** « laptop » → « un ordinateur portable » ; un nom inconnu est rendu tel quel. */
export function nomFrancais(categorie) {
  const n = NOMS[categorie];
  return n ? n[0] : categorie;
}

/** [{nom:"cup"}, {nom:"cup"}, {nom:"laptop"}] → « deux tasses et un ordinateur portable » */
export function enumerer(objets) {
  const CHIFFRES = ["", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix"];
  const comptes = new Map();
  for (const o of objets) comptes.set(o.nom, (comptes.get(o.nom) || 0) + 1);
  const morceaux = [...comptes].map(([categorie, n]) => {
    const noms = NOMS[categorie];
    if (!noms) return `${n > 1 ? n + " " : ""}${categorie}`;
    if (n === 1) return noms[0];
    return `${CHIFFRES[n] || n} ${noms[1]}`;
  });
  if (morceaux.length <= 1) return morceaux[0] || "";
  return morceaux.slice(0, -1).join(", ") + " et " + morceaux[morceaux.length - 1];
}
