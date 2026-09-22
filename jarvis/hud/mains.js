// Les mains (v3, consigne 5) : la caméra, MediaPipe en local, et ce que les gestes commandent.
//
// Règles de la v3 : la caméra est ÉTEINTE par défaut, elle demande l'autorisation avant la première image, rien
// n'est enregistré (l'image ne quitte pas la page, aucune trame n'est gardée), et un voyant dit quand elle est
// allumée. Tout tourne sur la machine : le moteur MediaPipe est dans hud/vendor/mediapipe/, le modèle dans
// modeles/mediapipe/hand_landmarker.task.
//
// La lecture des gestes est dans gestes.js (calcul pur, testable en rejouant des points).
import { lire, etatVide } from "./gestes.js";

const MODELE = "/modeles/mediapipe/hand_landmarker.task";
const VENDOR = "/hud/vendor/mediapipe";
const DELEGATE = new URLSearchParams(location.search).get("mains_gpu") ? "GPU" : "CPU";
const CADENCE_MS = 33;                  // ~30 lectures par seconde : assez pour la main, léger pour le HUD
const SECOURS_MS = 2000;                // une lecture qui ne revient pas ne doit pas bloquer les suivantes

export function creerMains({ reacteur, panneaux, note, reveiller, sons }) {
  let ouvrier = null, flux = null, video = null, tourne = false, derniere = 0, boucle = 0, occupe = false, secours = 0;
  let curseur = null, etat = etatVide(), pris = null, echelle = 1;
  const compte = { images: 0, gestes: 0, ms: 0, boucles: 0, envoyees: 0, dernierGeste: "", souci: "" };

  function creerCurseur() {
    curseur = document.createElement("div");
    curseur.id = "curseur-main";
    curseur.innerHTML = '<span class="anneau"></span><span class="point"></span>';
    document.body.appendChild(curseur);
  }

  function placerCurseur(x, y, pince) {
    if (!curseur) creerCurseur();
    curseur.style.transform = `translate(${x * innerWidth}px, ${y * innerHeight}px)`;
    curseur.classList.toggle("pince", !!pince);
    curseur.classList.add("visible");
  }

  // MediaPipe tourne dans un fil à part (mains_ouvrier.js) : le HUD ne s'arrête jamais pour lire une main
  function charger() {
    return new Promise((ok, ko) => {
      ouvrier = new Worker(new URL("./mains_ouvrier.js", import.meta.url));   // fil classique : voir mains_ouvrier.js
      ouvrier.onmessage = e => {
        const d = e.data;
        if (d.type === "pret") return ok(true);
        if (d.type === "erreur") { compte.souci = d.message; note("gestes : " + d.message); return ko(new Error(d.message)); }
        if (d.type === "mains") {
          occupe = false;
          clearTimeout(secours);
          compte.images++;
          compte.ms = Math.round(d.ms);
          // l'image de la caméra est en miroir : on retourne x pour que la main aille du bon côté
          const mains = d.mains.map(points => points.map(p => ({ x: 1 - p.x, y: p.y, z: p.z })));
          appliquer(lire(etat, mains, d.ts / 1000));
          if (!mains.length && curseur) curseur.classList.remove("visible");
        }
      };
      ouvrier.onerror = e => { compte.souci = e.message || "fil des mains"; note("gestes : " + compte.souci); ko(new Error(compte.souci)); };
      ouvrier.onmessageerror = e => { compte.souci = "message refusé par le fil des mains"; };
      ouvrier.postMessage({ type: "init", vendor: VENDOR, modele: MODELE, delegate: DELEGATE });
    });
  }

  // --- ce que chaque geste commande ---
  function sousLeCurseur(x, y) {
    const cible = document.elementFromPoint(x * innerWidth, y * innerHeight);
    const panneau = cible ? cible.closest(".holo") : null;
    return panneau && panneau.closest("#panneaux") ? panneau : null;
  }

  function appliquer(gestes) {
    for (const g of gestes) {
      if (g.type !== "curseur") { compte.gestes++; compte.dernierGeste = g.type; }
      switch (g.type) {
        case "curseur":
          placerCurseur(g.x, g.y, g.pince);
          if (pris) deplacer(g.x, g.y);
          break;
        case "pince_debut":
          if (g.main === 0) attraper(g.x, g.y);
          break;
        case "pince_fin":
          if (g.main === 0) lacher();
          break;
        case "rotation":
          reacteur.tournerHologramme(-g.delta * 2.2);
          break;
        case "zoom": {
          echelle = Math.min(2.2, Math.max(0.5, echelle * g.facteur));
          reacteur.echelleHologramme(echelle);
          break;
        }
        case "balayage":
          if (reacteur.etatHologramme.visible) { reacteur.cacherHologramme(); note("geste : hologramme retiré"); }
          else if (panneaux.nombre) { panneaux.fermerTout(); note("geste : panneaux fermés"); }
          if (sons) sons.jouer("extinction", reacteur.themeActuel);
          break;
        case "reveil":
          note(`geste : main ouverte ${g.tenue} s, je vous écoute`);
          reveiller();
          break;
      }
    }
  }

  function attraper(x, y) {
    const panneau = sousLeCurseur(x, y);
    if (panneau) {
      pris = { quoi: "panneau", element: panneau, depart: { x, y },
               origine: (panneau.style.transform.match(/-?\d+(\.\d+)?/g) || [0, 0]).map(Number) };
      panneau.classList.add("attrape");
      note("geste : panneau attrapé");
    } else if (reacteur.etatHologramme.visible) {
      pris = { quoi: "hologramme", depart: { x, y } };
      note("geste : hologramme attrapé");
    }
    if (pris && sons) sons.jouer("panneau", reacteur.themeActuel);
  }

  function deplacer(x, y) {
    if (!pris) return;
    const dx = x - pris.depart.x, dy = y - pris.depart.y;
    if (pris.quoi === "panneau") {
      pris.element.style.transform = `translate(${pris.origine[0] + dx * innerWidth}px, ${pris.origine[1] + dy * innerHeight}px)`;
    } else {
      reacteur.deplacerHologramme(dx * 4, -dy * 3);
    }
  }

  function lacher() {
    if (pris && pris.quoi === "panneau") pris.element.classList.remove("attrape");
    pris = null;
  }

  async function image() {
    if (!tourne) return;
    compte.boucles++;
    const maintenant = performance.now();
    if (!occupe && maintenant - derniere >= CADENCE_MS && video.readyState >= 2) {
      derniere = maintenant;
      occupe = true;
      clearTimeout(secours);
      secours = setTimeout(() => { occupe = false; compte.souci = "lecture des mains sans réponse"; }, SECOURS_MS);
      try {
        const bitmap = await createImageBitmap(video);            // ~0,2 ms, puis tout se passe dans l'autre fil
        ouvrier.postMessage({ type: "image", image: bitmap, ts: Math.round(maintenant) }, [bitmap]);
        compte.envoyees++;
      } catch (e) {
        occupe = false;
        compte.souci = e.message;
        note("gestes : " + e.message);
      }
    }
    boucle = requestAnimationFrame(image);
  }

  return {
    get actif() { return tourne; },
    get compteurs() { return { ...compte, mains: etat.mains.length, video: video ? video.readyState : -1 }; },
    async demarrer() {
      if (tourne) return true;
      try {
        if (!ouvrier) await charger();
        flux = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: "user" } });
        video = document.createElement("video");
        video.autoplay = true; video.playsInline = true; video.muted = true; video.srcObject = flux;
        await video.play();
        etat = etatVide();
        tourne = true;
        document.body.classList.add("gestes");
        note("gestes : caméra allumée, rien n'est enregistré");
        boucle = requestAnimationFrame(image);
        return true;
      } catch (e) {
        note("gestes : " + (e.name === "NotAllowedError" ? "caméra refusée" : e.message));
        arreter();
        return false;
      }
    },
    arreter() {
      tourne = false;
      cancelAnimationFrame(boucle);
      if (flux) flux.getTracks().forEach(p => p.stop());        // la caméra s'éteint pour de bon
      flux = null; video = null; pris = null; occupe = false;
      document.body.classList.remove("gestes");
      if (curseur) curseur.classList.remove("visible");
    },
    // pour les tests : rejouer des mains sans caméra
    rejouer(mains, t) { const g = lire(etat, mains, t); appliquer(g); return g; },
    remettre() { etat = etatVide(); pris = null; echelle = 1; compte.images = 0; compte.gestes = 0; },
  };
}
