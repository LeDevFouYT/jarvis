// Le scan de la pièce (v3, consigne 6) : « scanne la pièce » ouvre la caméra le temps du scan, fait descendre une
// ligne de balayage sur l'image, puis pose un cadre animé et son nom sur chaque objet reconnu.
//
// Règles de la v3 : la caméra ne s'allume que pour ce scan (et s'éteint seule à la fin), rien n'est enregistré —
// l'image ne quitte pas la page, aucune trame n'est gardée, seuls les NOMS trouvés sont dits. Le modèle
// (EfficientDet-Lite0, 80 catégories COCO) tourne en local dans le fil de vision, comme les mains.
import { enumerer, nomFrancais } from "./objets.js";

const MODELE = "/modeles/mediapipe/efficientdet_lite0_int8.tflite";
const VENDOR = "/hud/vendor/mediapipe";
const BALAYAGE_MS = 2200;        // la ligne descend en 2,2 s
const LECTURE_MS = 200;          // une lecture d'objets toutes les 200 ms pendant le balayage
const AFFICHAGE_MS = 9000;       // les cadres restent ensuite visibles neuf secondes

export function creerScan({ note, dire, sons, reacteur, delegate = "CPU" }) {
  let ouvrier = null, pret = false, flux = null, video = null, boite = null, minuteur = 0, fin = 0;
  let enCours = false, occupe = false, trouves = new Map();
  const compte = { lectures: 0, ms: 0, objets: 0, souci: "" };

  function creerBoite() {
    boite = document.createElement("div");
    boite.id = "scan";
    boite.innerHTML = '<div class="image"><video muted playsinline></video><div class="ligne"></div>'
      + '<div class="cadres"></div></div><div class="legende">scan de la pièce</div>';
    document.body.appendChild(boite);
    video = boite.querySelector("video");
  }

  function charger() {
    return new Promise((ok, ko) => {
      if (pret) return ok(true);
      ouvrier = ouvrier || new Worker(new URL("./mains_ouvrier.js", import.meta.url));  // fil classique : voir ce fichier
      ouvrier.onmessage = e => {
        const d = e.data;
        if (d.type === "pret_objets") { pret = true; return ok(true); }
        if (d.type === "erreur") { compte.souci = d.message; note("scan : " + d.message); return ko(new Error(d.message)); }
        if (d.type === "objets") {
          occupe = false;
          compte.lectures++;
          compte.ms = Math.round(d.ms);
          poser(d.objets);
        }
      };
      ouvrier.onerror = e => { compte.souci = e.message || "fil de vision"; ko(new Error(compte.souci)); };
      ouvrier.postMessage({ type: "init_objets", vendor: VENDOR, modele: MODELE, delegate, seuil: 0.4 });
    });
  }

  // un cadre par objet : on garde la meilleure lecture de chaque objet (même nom, même endroit)
  function poser(objets) {
    const cadres = boite.querySelector(".cadres");
    for (const o of objets) {
      const cle = o.nom + "@" + Math.round(o.x * 6) + "," + Math.round(o.y * 6);
      const avant = trouves.get(cle);
      if (avant && avant.score >= o.score) continue;
      trouves.set(cle, o);
      let cadre = avant && avant.element;
      if (!cadre) {
        cadre = document.createElement("div");
        cadre.className = "cadre";
        cadre.innerHTML = '<span class="coin hg"></span><span class="coin hd"></span><span class="coin bg"></span>'
          + '<span class="coin bd"></span><span class="nom"></span>';
        cadres.appendChild(cadre);
        if (sons) sons.jouer("panneau", reacteur.themeActuel);
      }
      o.element = cadre;
      cadre.querySelector(".nom").textContent = `${nomFrancais(o.nom)} · ${Math.round(o.score * 100)} %`;
      // l'image est en miroir (comme un miroir, plus naturel) : le cadre suit
      cadre.style.left = ((1 - o.x - o.l) * 100) + "%";
      cadre.style.top = (o.y * 100) + "%";
      cadre.style.width = (o.l * 100) + "%";
      cadre.style.height = (o.h * 100) + "%";
    }
    compte.objets = trouves.size;
  }

  function arreter(silencieux = false) {
    clearInterval(minuteur);
    clearTimeout(fin);
    enCours = false;
    occupe = false;
    if (flux) flux.getTracks().forEach(p => p.stop());          // la caméra s'éteint pour de bon
    flux = null;
    if (boite) { boite.classList.remove("visible"); setTimeout(() => { if (!enCours && boite) boite.remove(); boite = null; }, 700); }
    if (!silencieux) note("scan : caméra éteinte");
  }

  return {
    get actif() { return enCours; },
    get compteurs() { return { ...compte, objets: trouves.size }; },
    get objets() { return [...trouves.values()].map(o => ({ nom: o.nom, score: +o.score.toFixed(2), x: +o.x.toFixed(3), y: +o.y.toFixed(3) })); },
    get phrase() { return enumerer([...trouves.values()]); },
    arreter,
    /** Ouvre la caméra, balaie, pose les cadres, puis rend la caméra. Rend la liste des objets trouvés. */
    async lancer() {
      if (enCours) return this.objets;
      trouves = new Map();
      compte.lectures = 0; compte.objets = 0; compte.souci = "";
      try {
        await charger();
        flux = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: "user" } });
      } catch (e) {
        note("scan : " + (e.name === "NotAllowedError" ? "caméra refusée" : e.message));
        arreter(true);
        return null;
      }
      if (!boite) creerBoite();
      video.srcObject = flux;
      await video.play();
      enCours = true;
      boite.classList.add("visible");
      boite.style.setProperty("--balayage", BALAYAGE_MS + "ms");
      boite.classList.add("balaye");
      note("scan : caméra allumée le temps du scan, rien n'est enregistré");
      if (sons) sons.jouer("reveil", reacteur.themeActuel);
      let t = 0;
      minuteur = setInterval(async () => {
        if (occupe || !video || video.readyState < 2) return;
        occupe = true;
        try {
          const bitmap = await createImageBitmap(video);
          ouvrier.postMessage({ type: "objets", image: bitmap, ts: (t += LECTURE_MS) }, [bitmap]);
        } catch (e) { occupe = false; compte.souci = e.message; }
      }, LECTURE_MS);
      await new Promise(r => setTimeout(r, BALAYAGE_MS + 400));
      clearInterval(minuteur);
      boite.classList.remove("balaye");
      const liste = this.objets;
      const phrase = this.phrase;
      note(liste.length ? "scan : " + phrase : "scan : rien de reconnu");
      if (dire) dire(phrase, liste);
      // la caméra est rendue tout de suite ; les cadres restent visibles un moment, sur la dernière image figée
      if (flux) flux.getTracks().forEach(p => p.stop());
      flux = null;
      boite.classList.add("fige");
      fin = setTimeout(() => arreter(true), AFFICHAGE_MS);
      enCours = false;
      return liste;
    },
  };
}
