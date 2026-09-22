// MediaPipe dans un fil à part (v3, consignes 5 et 6) : les mains, et les objets de la pièce (scan). Sur le fil principal, une lecture de main coûte ~9 ms : à 30 par
// seconde, une image du HUD sur quatre arrivait en retard (p99 10,3 ms le 20/09, budget 144 Hz = 6,9 ms). Ici le
// modèle tourne dans un worker avec son propre contexte graphique ; le HUD ne fait que lui passer une image
// (createImageBitmap, ~0,2 ms) et recevoir 21 points par main.
//
// Ce fil est CLASSIQUE (pas « module ») : MediaPipe charge son moteur avec importScripts, interdit dans un fil
// module (« Module scripts don't support importScripts() », 20/09). L'import du paquet se fait donc à la main.
//
// Messages reçus : {type:"init"|"init_objets", vendor, modele} puis {type:"image"|"objets", image: ImageBitmap, ts}
// Messages envoyés : {type:"pret"|"pret_objets"} | {type:"mains", …} | {type:"objets", objets, ts, ms} | {type:"erreur"}
let landmarker = null, detecteur = null;

self.onmessage = async (e) => {
  const d = e.data;
  try {
    if (d.type === "init") {
      const { FilesetResolver, HandLandmarker } = await import(`${d.vendor}/vision_bundle.mjs`);
      const fileset = await FilesetResolver.forVisionTasks(d.vendor);
      landmarker = await HandLandmarker.createFromOptions(fileset, {
        // PROCESSEUR par défaut : avec l'accélération graphique, la première lecture ne revient jamais dans un fil
        // (constaté le 20/09, Edge sans fenêtre, page qui tient déjà un contexte WebGL). Ici le coût ne touche pas
        // le HUD, puisque c'est un autre fil.
        baseOptions: { modelAssetPath: d.modele, delegate: d.delegate || "CPU" },
        runningMode: "VIDEO", numHands: 2, minHandDetectionConfidence: 0.5, minTrackingConfidence: 0.5,
      });
      self.postMessage({ type: "pret" });
    } else if (d.type === "init_objets") {
      const { FilesetResolver, ObjectDetector } = await import(`${d.vendor}/vision_bundle.mjs`);
      const fileset = await FilesetResolver.forVisionTasks(d.vendor);
      detecteur = await ObjectDetector.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: d.modele, delegate: d.delegate || "CPU" },
        runningMode: "VIDEO", scoreThreshold: d.seuil || 0.4, maxResults: 8,
      });
      self.postMessage({ type: "pret_objets" });
    } else if (d.type === "objets") {
      if (!detecteur) { d.image.close(); return; }
      const t = performance.now();
      const r = detecteur.detectForVideo(d.image, d.ts);
      const largeur = d.image.width, hauteur = d.image.height;
      d.image.close();
      self.postMessage({ type: "objets", ts: d.ts, ms: performance.now() - t,
        objets: (r.detections || []).map(o => ({
          nom: (o.categories[0] || {}).categoryName || "?", score: (o.categories[0] || {}).score || 0,
          x: o.boundingBox.originX / largeur, y: o.boundingBox.originY / hauteur,
          l: o.boundingBox.width / largeur, h: o.boundingBox.height / hauteur })) });
    } else if (d.type === "image") {
      if (!landmarker) { d.image.close(); return; }
      const t = performance.now();
      const r = landmarker.detectForVideo(d.image, d.ts);
      d.image.close();
      self.postMessage({ type: "mains", ts: d.ts, ms: performance.now() - t,
                         mains: (r.landmarks || []).map(p => p.map(q => ({ x: q.x, y: q.y, z: q.z }))) });
    }
  } catch (err) {
    if (d.image) try { d.image.close(); } catch (_) {}
    self.postMessage({ type: "erreur", message: String(err && err.message || err) });
  }
};
