// Les panneaux holographiques : un seul système pour tous les outils.
// Un événement {type: "panneau", genre, titre, ...} (jarvis/outils/panneaux.py) ouvre un panneau qui se déplie
// avec un léger scintillement, puis anime son contenu selon le genre :
//   texte · liste · graphique · images · frise · recherche · page (et « formulaire », utilisé par les réglages).
// Petits panneaux : empilés à droite du réacteur, trois au plus. Grands (page, formulaire) : seuls, plus larges.
// « constellation » : la mémoire longue en 3D, une étoile par souvenir ; celles que le cerveau utilise s'allument.
import * as THREE from "three";

const GRANDS = new Set(["page", "formulaire"]);
const MAX_PETITS = 3;

function el(balise, classe, texte) {
  const e = document.createElement(balise);
  if (classe) e.className = classe;
  if (texte !== undefined && texte !== null) e.textContent = texte;
  return e;
}

// ------------------------------------------------------------------------------------------ rendus par genre
const RENDUS = {
  texte(corps, e) {
    const bloc = el("div", "h-texte");
    (e.paragraphes || []).forEach((p, i) => { const x = el("p", "h-apparait", p); x.style.animationDelay = (180 + i * 110) + "ms"; bloc.appendChild(x); });
    if (e.source) bloc.appendChild(el("small", "h-source", e.source));
    corps.appendChild(bloc);
  },

  liste(corps, e) {
    const ul = el("ol", "h-liste");
    const elements = e.elements || [];
    if (!elements.length) ul.appendChild(el("li", "h-vide", e.vide || "Rien à afficher."));
    elements.slice(0, 40).forEach((x, i) => {
      const li = el("li", "h-apparait"); li.style.animationDelay = (160 + i * 55) + "ms";
      li.appendChild(el("span", "h-num", String(i + 1).padStart(2, "0")));
      const t = el("div", "h-item");
      t.appendChild(el("b", "", x.titre));
      if (x.detail) t.appendChild(el("small", "", x.detail));
      li.appendChild(t);
      if (x.meta) li.appendChild(el("span", "h-meta", x.meta));
      if (x.url) { li.classList.add("cliquable"); li.onclick = () => window.open(x.url, "_blank"); }
      ul.appendChild(li);
    });
    corps.appendChild(ul);
  },

  graphique(corps, e) {
    const bloc = el("div", "h-graphique");
    (e.jauges || []).forEach((j, i) => {
      const ligne = el("div", "h-jauge h-apparait" + (j.alerte ? " alerte" : "")); ligne.style.animationDelay = (150 + i * 70) + "ms";
      const tete = el("div", "h-jauge-tete");
      tete.appendChild(el("span", "", j.nom));
      const val = el("b", "", "0"); tete.appendChild(val);
      const piste = el("div", "h-piste"), barre = el("i");
      for (let k = 1; k < 10; k++) { const g = el("u"); g.style.left = (k * 10) + "%"; piste.appendChild(g); }
      piste.appendChild(barre); ligne.append(tete, piste); bloc.appendChild(ligne);
      const ratio = Math.max(0, Math.min(1, (j.valeur || 0) / (j.max || 1)));
      const decimales = Number.isInteger(j.valeur) ? 0 : 1;
      const suffixe = (j.unite === "%" || j.unite === "°C") ? ` ${j.unite}` : ` / ${j.max} ${j.unite || ""}`;
      // la barre et le chiffre montent ensemble, après le dépliage
      setTimeout(() => {
        barre.style.transform = `scaleX(${ratio})`;
        const t0 = performance.now(), duree = 900;
        (function compter(t) {
          const k = Math.min(1, (t - t0) / duree), f = 1 - Math.pow(1 - k, 3);
          val.textContent = ((j.valeur || 0) * f).toFixed(decimales).replace(".", ",") + suffixe;
          if (k < 1) requestAnimationFrame(compter);
        })(t0);
      }, 260 + i * 70);
    });
    if (e.courbe && e.courbe.length > 2) {
      const L = 600, H = 120, n = e.courbe.length, max = Math.max(100, ...e.courbe);
      const pts = e.courbe.map((v, i) => `${(i / (n - 1) * L).toFixed(1)},${(H - v / max * (H - 8) - 4).toFixed(1)}`).join(" ");
      const fig = el("figure", "h-courbe h-apparait"); fig.style.animationDelay = (200 + (e.jauges || []).length * 70) + "ms";
      fig.innerHTML = `<svg viewBox="0 0 ${L} ${H}" preserveAspectRatio="none">
          <defs><linearGradient id="hc" x1="0" y1="0" x2="0" y2="1"><stop offset="0" style="stop-color: var(--cyan)" stop-opacity=".35"/><stop offset="1" style="stop-color: var(--cyan)" stop-opacity="0"/></linearGradient></defs>
          <polygon class="aire" points="0,${H} ${pts} ${L},${H}" fill="url(#hc)"/>
          <polyline class="trait" pathLength="1" points="${pts}" fill="none" style="stroke: var(--cyan)" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
      fig.appendChild(el("figcaption", "", e.legende_courbe || ""));
      bloc.appendChild(fig);
    }
    corps.appendChild(bloc);
  },

  // un nuage de vidéos : la date en x, les vues en y (échelle logarithmique) ; les exceptions (> 3 × la médiane) brillent
  nuage(corps, e) {
    const pts = (e.points || []).filter(p => p.quand && p.vues >= 0);
    if (!pts.length) { corps.appendChild(el("p", "h-vide", "Aucune vidéo.")); return; }
    const L = 640, H = 260, g = 46, d = 14, h = 14, b = 30;
    const t0 = Math.min(...pts.map(p => p.quand)), t1 = Math.max(...pts.map(p => p.quand)) || t0 + 1;
    const lg = v => Math.log10(Math.max(1, v));
    const vmin = Math.min(...pts.map(p => lg(p.vues)), e.mediane ? lg(e.mediane) : 9), vmax = Math.max(...pts.map(p => lg(p.vues)), e.mediane ? lg(e.mediane * 3) : 0);
    const bas = Math.floor(vmin), haut = Math.max(bas + 1, Math.ceil(vmax));
    const X = t => g + (t1 === t0 ? 0.5 : (t - t0) / (t1 - t0)) * (L - g - d), Y = v => h + (1 - (lg(v) - bas) / (haut - bas)) * (H - h - b);
    const court = v => v >= 1e6 ? (v / 1e6).toLocaleString("fr", { maximumFractionDigits: 1 }) + " M" : v >= 1e3 ? Math.round(v / 1e3) + " k" : String(v);
    let svg = `<svg viewBox="0 0 ${L} ${H}" class="h-nuage-svg"><defs><filter id="lueur" x="-2" y="-2" width="5" height="5"><feGaussianBlur stdDeviation="4"/></filter></defs>`;
    for (let k = bas; k <= haut; k++) svg += `<line x1="${g}" x2="${L - d}" y1="${Y(10 ** k)}" y2="${Y(10 ** k)}" class="grille"/><text x="${g - 6}" y="${Y(10 ** k) + 4}" class="axe" text-anchor="end">${court(10 ** k)}</text>`;
    if (e.mediane) {
      svg += `<line x1="${g}" x2="${L - d}" y1="${Y(e.mediane)}" y2="${Y(e.mediane)}" class="mediane"/><text x="${L - d}" y="${Y(e.mediane) - 5}" class="axe" text-anchor="end">médiane ${court(Math.round(e.mediane))}</text>`;
      svg += `<line x1="${g}" x2="${L - d}" y1="${Y(e.mediane * 3)}" y2="${Y(e.mediane * 3)}" class="seuil"/><text x="${L - d}" y="${Y(e.mediane * 3) - 5}" class="axe" text-anchor="end">3 × médiane</text>`;
    }
    const jour = t => new Date(t * 1000).toLocaleDateString("fr", { day: "numeric", month: "short" });
    svg += `<text x="${g}" y="${H - 8}" class="axe">${jour(t0)}</text><text x="${L - d}" y="${H - 8}" class="axe" text-anchor="end">${jour(t1)}</text>`;
    pts.forEach((p, i) => {
      const x = X(p.quand).toFixed(1), y = Y(p.vues).toFixed(1);
      if (p.brille) svg += `<circle cx="${x}" cy="${y}" r="11" class="halo" filter="url(#lueur)" style="animation-delay:${400 + i * 30}ms"/>`;
      svg += `<circle cx="${x}" cy="${y}" r="${p.brille ? 6 : 4}" class="point${p.brille ? " brille" : ""}" data-i="${i}" style="animation-delay:${300 + i * 30}ms"/>`;
    });
    svg += "</svg>";
    const fig = el("figure", "h-nuage"); fig.innerHTML = svg;
    const info = el("div", "h-nuage-info", `${pts.length} vidéos · ${pts.filter(p => p.brille).length} au-dessus de 3 × la médiane · survolez un point`);
    fig.querySelectorAll("circle.point").forEach(c => {
      const p = pts[+c.dataset.i];
      c.addEventListener("mouseenter", () => { info.textContent = `« ${p.titre} » · ${p.vues.toLocaleString("fr")} vues · ${jour(p.quand)}` + (p.ratio ? ` · ${p.ratio.toLocaleString("fr")} × la médiane` : ""); });
      if (p.url) c.addEventListener("click", () => window.open(p.url, "_blank"));
    });
    corps.append(fig, info);
    if (e.source) corps.appendChild(el("small", "h-source", e.source));
  },

  // des barres horizontales, la plus haute pleine largeur
  barres(corps, e) {
    const bs = e.barres || [];
    if (!bs.length) { corps.appendChild(el("p", "h-vide", "Rien à afficher.")); return; }
    const max = Math.max(...bs.map(x => x.valeur), 1);
    const bloc = el("div", "h-barres");
    bs.forEach((x, i) => {
      const ligne = el("div", "h-barre h-apparait" + (x.brille ? " brille" : "")); ligne.style.animationDelay = (150 + i * 60) + "ms";
      const tete = el("div", "h-jauge-tete");
      tete.append(el("span", "", x.nom + (x.detail ? ` · ${x.detail}` : "")), el("b", "", Math.round(x.valeur).toLocaleString("fr") + (e.unite ? " " + e.unite : "")));
      const piste = el("div", "h-piste"), barre = el("i"); piste.appendChild(barre);
      ligne.append(tete, piste); bloc.appendChild(ligne);
      setTimeout(() => { barre.style.transform = `scaleX(${Math.max(0, x.valeur) / max})`; }, 260 + i * 60);
    });
    corps.appendChild(bloc);
  },

  // la vidéo tournée par Jarvis (consigne 8) : d'abord une barre de progression, puis le film en boucle
  video(corps, e) {
    const cadre = el("div", "h-video");
    const barre = el("div", "h-progression");
    const jauge = el("span", "h-avance");
    const texte = el("span", "h-etape", e.etape || "préparation");
    barre.append(jauge, texte);
    cadre.appendChild(barre);
    const film = el("video");
    film.muted = true; film.loop = true; film.autoplay = true; film.playsInline = true;
    film.style.display = "none";
    cadre.appendChild(film);
    corps.appendChild(cadre);
    // le panneau se met à jour tout seul quand l'avancement ou la vidéo arrivent
    cadre.majVideo = d => {
      if (d.pourcent !== undefined) {
        jauge.style.width = Math.max(2, Math.min(100, d.pourcent)) + "%";
        texte.textContent = (d.etape || "image ") + (d.pourcent !== undefined ? ` ${Math.round(d.pourcent)} %` : "");
      }
      if (d.url) {
        film.src = d.url;
        film.style.display = "";
        barre.classList.add("finie");
        texte.textContent = d.duree ? `${d.duree} s · ${d.calcul || "?"} s de calcul` : "prête";
        film.play().catch(() => {});
      }
    };
    if (e.url) cadre.majVideo(e);
    else if (e.pourcent !== undefined) cadre.majVideo(e);
  },

  // le tchat du direct (mode live) : les messages défilent, et ce que Jarvis répond est mis en avant
  tchat(corps, e) {
    const bloc = el("div", "h-tchat");
    const fil = el("div", "h-tchat-fil");
    const pied = el("div", "h-tchat-pied");
    const compteur = el("span", "h-tchat-compte", "en attente du tchat…");
    pied.appendChild(compteur);
    bloc.append(fil, pied);
    corps.appendChild(bloc);
    const MAX = 40;                       // au-delà, les plus vieux sortent : un direct dure des heures
    bloc.majTchat = d => {
      if (d.ligne) {
        const l = el("div", "h-tchat-ligne " + (d.ligne.genre || "message"));
        if (d.ligne.auteur) l.appendChild(el("span", "h-tchat-qui", d.ligne.auteur));
        l.appendChild(el("span", "h-tchat-texte", d.ligne.texte || ""));
        fil.appendChild(l);
        while (fil.children.length > MAX) fil.removeChild(fil.firstChild);
        fil.scrollTop = fil.scrollHeight;
      }
      if (d.compte) {
        const c = d.compte;
        compteur.textContent = `${c.messages || 0} messages · ${c.reponses || 0} réponses · `
          + `${c.accueils || 0} accueils · ${c.spectateurs_connus || 0} personnes`;
      }
      if (d.fini) bloc.classList.add("fini");
    };
    if (e.lignes) e.lignes.forEach(ligne => bloc.majTchat({ ligne }));
    if (e.compte) bloc.majTchat({ compte: e.compte });
  },

  images(corps, e, outils) {
    const grille = el("div", "h-images" + ((e.images || []).length === 1 ? " seule" : ""));
    (e.images || []).slice(0, 6).forEach((im, i) => {
      const fig = el("figure", "h-image"); fig.style.animationDelay = (220 + i * 140) + "ms";
      const img = el("img"); img.src = im.url; img.alt = im.legende || "";
      img.onclick = () => outils.agrandir(im.url);
      fig.append(img, el("span", "h-scan"));
      if (im.legende) fig.appendChild(el("figcaption", "", im.legende));
      grille.appendChild(fig);
    });
    corps.appendChild(grille);
  },

  frise(corps, e, outils) {
    if (e.video) return RENDUS.friseVideo(corps, e, outils);
    const evts = (e.evenements || []).slice().sort((a, b) => a.quand - b.quand).slice(0, 8);
    const bloc = el("div", "h-frise");
    if (!evts.length) { bloc.appendChild(el("p", "h-vide", e.vide || "Rien de prévu.")); corps.appendChild(bloc); return; }
    const axe = el("div", "h-axe"); bloc.appendChild(axe);
    const maintenant = Date.now() / 1000;
    evts.forEach((x, i) => {
      const pos = evts.length === 1 ? 50 : 6 + (i / (evts.length - 1)) * 88;
      const bord = evts.length > 1 && i === 0 ? " debut" : evts.length > 1 && i === evts.length - 1 ? " fin" : "";
      const point = el("div", "h-point" + (i % 2 ? " bas" : "") + bord); point.style.left = pos + "%"; point.style.animationDelay = (500 + i * 160) + "ms";
      const d = new Date(x.quand * 1000), ecart = Math.round((x.quand - maintenant) / 60);
      const quand = `${d.getHours()} h ${String(d.getMinutes()).padStart(2, "0")}`;
      const dans = ecart < 0 ? "passé" : ecart < 60 ? `dans ${ecart} min` : ecart < 1440 ? `dans ${Math.round(ecart / 60)} h` : `le ${d.getDate()}/${d.getMonth() + 1}`;
      const etiquette = el("div", "h-etiquette");
      etiquette.append(el("small", "", `${quand} · ${dans}`), el("b", "", x.titre));
      if (x.detail) etiquette.appendChild(el("span", "", x.detail));
      point.appendChild(etiquette); bloc.appendChild(point);
    });
    corps.appendChild(bloc);
  },

  // une vidéo résumée : le résumé, ses moments clés posés sur sa durée (l'instant sur l'axe, le titre dans la liste) ;
  // un clic ouvre la vidéo intégrée à cet instant
  friseVideo(corps, e, outils) {
    const v = e.video, duree = Math.max(1, v.duree || 1);
    const mmss = s => { s = Math.round(s); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), r = String(s % 60).padStart(2, "0");
      return h ? `${h}:${String(m).padStart(2, "0")}:${r}` : `${m}:${r}`; };
    if (v.resume) { const p = el("p", "h-resume h-apparait", v.resume); p.style.animationDelay = "160ms"; corps.appendChild(p); }
    const moments = (e.evenements || []).slice().sort((a, b) => a.t - b.t);
    // le propriétaire interdit parfois le lecteur intégré (« vidéo non disponible ») : on ouvre alors YouTube au bon instant
    const ouvrir = x => v.integrable === false ? window.open(`${v.lien}&t=${Math.floor(x.t)}s`, "_blank")
      : outils.ouvrir({ genre: "page", titre: `${mmss(x.t)} · ${x.titre}`, url: x.url, externe: `${v.lien}&t=${Math.floor(x.t)}s`, retour: e });
    const bloc = el("div", "h-frise video");
    bloc.append(el("div", "h-axe"), el("span", "h-borne debut", "0:00"), el("span", "h-borne fin", mmss(duree)));
    moments.forEach((x, i) => {
      const point = el("div", "h-point cliquable" + (i % 2 ? " bas" : ""));
      point.style.left = (2 + (x.t / duree) * 96) + "%"; point.style.animationDelay = (500 + i * 140) + "ms";
      point.title = x.titre;
      const etiquette = el("div", "h-etiquette"); etiquette.appendChild(el("small", "", mmss(x.t)));
      point.appendChild(etiquette); point.onclick = () => ouvrir(x);
      bloc.appendChild(point);
    });
    corps.appendChild(bloc);
    const liste = el("ol", "h-liste h-moments");
    moments.forEach((x, i) => {
      const li = el("li", "h-apparait cliquable"); li.style.animationDelay = (700 + i * 60) + "ms";
      li.append(el("span", "h-num", mmss(x.t)), el("div", "h-item", x.titre));
      li.onclick = () => ouvrir(x); liste.appendChild(li);
    });
    corps.appendChild(liste);
    if (v.chaine) corps.appendChild(el("small", "h-source", `${v.chaine} · résumé sur cette machine, cliquez un moment pour y aller`));
  },

  recherche(corps, e, outils) {
    const liste = el("div", "h-resultats");
    if (!(e.resultats || []).length) liste.appendChild(el("p", "h-vide", "Aucun résultat."));
    (e.resultats || []).forEach((r, i) => {
      const d = el("div", "h-resultat h-apparait"); d.style.animationDelay = (160 + i * 70) + "ms";
      d.append(el("b", "", r.titre), el("small", "", r.domaine), el("span", "", r.extrait));
      d.onclick = () => outils.ouvrir({ genre: "page", titre: r.titre, url: r.url, retour: e });
      liste.appendChild(d);
    });
    corps.appendChild(liste);
  },

  page(corps, e) {
    const f = el("iframe"); f.src = e.url;
    f.allow = "autoplay; fullscreen; encrypted-media; picture-in-picture";
    // YouTube refuse un lecteur intégré sans référent (erreur 153) : l'origine seule lui suffit, jamais le chemin
    f.referrerPolicy = /youtube(-nocookie)?\.com\/embed\//.test(e.url || "") ? "strict-origin-when-cross-origin" : "no-referrer";
    corps.appendChild(f);
    corps.appendChild(el("div", "h-note", "Si la page reste vide, le site refuse l'affichage intégré : bouton « navigateur »."));
  },

  formulaire(corps, e) {
    if (e.construire) e.construire(corps);
  },

  // la mémoire longue : une étoile par souvenir, placée par le sens (ACP des plongements, calculée par le serveur),
  // reliée à sa plus proche voisine. Survol : le souvenir. Souvenirs utilisés : l'étoile s'allume en ambre.
  constellation(corps, e, outils) {
    const etoiles = e.etoiles || [];
    const bloc = el("div", "h-constellation");
    const ciel = el("div", "h-ciel");
    const info = el("div", "h-etoile-info", etoiles.length ? "survolez une étoile" : "");
    const allumes = el("div", "h-allumes");
    const pied = el("div", "h-constellation-pied", `${etoiles.length} souvenir${etoiles.length > 1 ? "s" : ""}`);
    bloc.append(ciel, info, allumes, pied);
    corps.appendChild(bloc);
    if (!etoiles.length) { ciel.appendChild(el("p", "h-vide", "Aucun souvenir pour l'instant. Dites « Jarvis, retiens que… ».")); return null; }

    const largeur = Math.max(320, corps.clientWidth - 36 || 700), hauteur = 330;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5));
    renderer.setSize(largeur, hauteur);
    ciel.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, largeur / hauteur, 0.1, 50);
    camera.position.set(0, 0.3, 4.4);
    camera.lookAt(0, 0, 0);
    const groupe = new THREE.Group();
    scene.add(groupe);

    const n = etoiles.length, pos = new Float32Array(n * 3), taille = new Float32Array(n), eclat = new Float32Array(n);
    const cible = new Float32Array(n), index = new Map();
    etoiles.forEach((s, i) => {
      pos.set((s.position || [0, 0, 0]).map(v => v * 1.45), i * 3);
      taille[i] = 7 + Math.min(10, (s.utilise || 0) * 1.5);
      index.set(s.id, i);
    });
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("aTaille", new THREE.BufferAttribute(taille, 1));
    geo.setAttribute("aEclat", new THREE.BufferAttribute(eclat, 1));
    const points = new THREE.Points(geo, new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      uniforms: { uRatio: { value: renderer.getPixelRatio() }, uTemps: { value: 0 } },
      vertexShader: `attribute float aTaille; attribute float aEclat; uniform float uRatio; uniform float uTemps; varying float vEclat;
        void main(){ vEclat = aEclat; vec4 mv = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = aTaille * (1.0 + aEclat * 1.3 + 0.08 * sin(uTemps * 2.0 + position.x * 9.0)) * uRatio * (4.0 / -mv.z);
          gl_Position = projectionMatrix * mv; }`,
      fragmentShader: `varying float vEclat;
        void main(){ float d = length(gl_PointCoord - 0.5); float coeur = smoothstep(0.16, 0.0, d); float halo = smoothstep(0.5, 0.0, d) * 0.55;
          vec3 c = mix(vec3(0.37, 0.89, 1.0), vec3(1.0, 0.76, 0.42), vEclat);
          gl_FragColor = vec4(mix(c, vec3(1.0), coeur * 0.8), (coeur + halo) * (0.7 + vEclat * 0.3)); }`,
    }));
    groupe.add(points);
    const segments = [];
    for (const [a, b] of e.liens || []) {
      if (!index.has(a) || !index.has(b)) continue;
      segments.push(...pos.slice(index.get(a) * 3, index.get(a) * 3 + 3), ...pos.slice(index.get(b) * 3, index.get(b) * 3 + 3));
    }
    if (segments.length) {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(segments), 3));
      groupe.add(new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0x5fe3ff, transparent: true, opacity: 0.22,
        blending: THREE.AdditiveBlending, depthWrite: false })));
    }

    function allumer(ids, faits) {
      cible.fill(0);
      (ids || []).forEach(id => { if (index.has(id)) cible[index.get(id)] = 1; });
      allumes.innerHTML = "";
      (faits || (ids || []).map(id => (etoiles[index.get(id)] || {}).fait).filter(Boolean)).forEach((f, i) => {
        const x = el("span", "h-allume h-apparait", f); x.style.animationDelay = (i * 90) + "ms"; allumes.appendChild(x);
      });
    }
    allumer(e.allumes || []);
    outils.panneau._allumer = allumer;

    const souris = new THREE.Vector2(9, 9), rayon = new THREE.Raycaster();
    rayon.params.Points.threshold = 0.09;
    renderer.domElement.addEventListener("pointermove", ev => {
      const r = renderer.domElement.getBoundingClientRect();
      souris.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    });
    renderer.domElement.addEventListener("pointerleave", () => souris.set(9, 9));

    let anim = 0, t0 = performance.now(), survol = -1;
    (function boucle(t) {
      anim = requestAnimationFrame(boucle);
      points.material.uniforms.uTemps.value = (t - t0) / 1000;
      groupe.rotation.y += 0.0022;
      groupe.rotation.x = Math.sin((t - t0) / 5200) * 0.18;
      let bouge = false;
      for (let i = 0; i < n; i++) {
        const v = eclat[i] + (cible[i] - eclat[i]) * 0.08;
        if (Math.abs(v - eclat[i]) > 0.001) { eclat[i] = v; bouge = true; }
      }
      if (bouge) geo.attributes.aEclat.needsUpdate = true;
      rayon.setFromCamera(souris, camera);
      const touche = rayon.intersectObject(points)[0];
      const i = touche ? touche.index : -1;
      if (i !== survol) {
        survol = i;
        info.textContent = i >= 0 ? `${etoiles[i].fait} · ${etoiles[i].date} · ${etoiles[i].source}` : "survolez une étoile";
      }
      renderer.render(scene, camera);
    })(t0);

    return () => { cancelAnimationFrame(anim); geo.dispose(); renderer.dispose(); renderer.forceContextLoss(); };
  },
};

// ------------------------------------------------------------------------------------------ le gestionnaire
export function creerPanneaux(zone, options = {}) {
  let compteur = 0, dernierFerme = null;
  const ouverts = [];

  function notifier() { options.surChangement && options.surChangement(ouverts.length, zone.classList.contains("large")); }
  // mode vidéo : un seul panneau à la fois (options.maxPetits le dit), sinon trois
  const maxPetits = () => (options.maxPetits ? options.maxPetits() : MAX_PETITS);

  function fermer(p, silencieux) {
    if (!p || p.classList.contains("ferme")) return;
    const i = ouverts.indexOf(p); if (i >= 0) ouverts.splice(i, 1);
    dernierFerme = p._evenement;
    p.classList.add("ferme");
    const f = p.querySelector("iframe"); if (f) f.src = "about:blank";
    if (p._detruire) setTimeout(p._detruire, 400);          // un contexte WebGL par constellation : rendu à la fermeture
    setTimeout(() => { p.remove(); if (!ouverts.some(x => x.classList.contains("grand"))) zone.classList.remove("large"); notifier(); }, 380);
    if (!silencieux) notifier();
  }

  function ouvrir(e) {
    let genre = e.genre === "youtube" ? "page" : e.genre;
    if (!RENDUS[genre]) genre = "texte";
    const grand = GRANDS.has(genre);
    if (e.cle) ouverts.filter(p => p._evenement && p._evenement.cle === e.cle).forEach(p => fermer(p, true));
    // un grand panneau remplace tout ; un petit ferme les grands et le plus ancien au-delà de trois
    if (grand) ouverts.slice().forEach(p => fermer(p, true));
    else {
      ouverts.filter(p => p.classList.contains("grand")).forEach(p => fermer(p, true));
      while (ouverts.length >= maxPetits()) fermer(ouverts[0], true);
    }
    zone.classList.toggle("large", grand);

    compteur++;
    const p = el("section", `holo genre-${genre}` + (grand ? " grand" : ""));
    p._evenement = e;
    const tete = el("header");
    tete.append(el("span", "h-index", String(compteur).padStart(2, "0")), el("h3", "", e.titre || genre),
                el("span", "h-genre", { texte: "texte", liste: "liste", graphique: "données", images: "images", frise: "frise",
                  recherche: "recherche", page: "page", formulaire: "réglages", constellation: "mémoire", nuage: "vidéos",
                  barres: "données", video: "vidéo" }[genre]));
    if (e.retour) { const b = el("button", "", "retour"); b.onclick = () => ouvrir(e.retour); tete.appendChild(b); }
    const externe = e.externe || (genre === "page" ? e.url : "");
    if (externe) { const b = el("button", "", "navigateur"); b.onclick = () => window.open(externe, "_blank"); tete.appendChild(b); }
    const x = el("button", "h-fermer", "×"); x.title = "fermer"; x.onclick = () => fermer(p); tete.appendChild(x);
    const corps = el("div", "h-corps");
    p.append(el("i", "h-coin hg"), el("i", "h-coin hd"), el("i", "h-coin bg"), el("i", "h-coin bd"),
             tete, corps, el("div", "h-balayage"), el("div", "h-eclair"));
    zone.prepend(p);                                   // le plus récent en haut (avant le rendu : le canvas 3D mesure sa largeur)
    try {
      const nettoyage = RENDUS[genre](corps, e, { ouvrir, agrandir: options.agrandir || (() => {}), panneau: p });
      if (typeof nettoyage === "function") p._detruire = nettoyage;
    } catch (err) { corps.appendChild(el("p", "h-vide", "Panneau illisible : " + err.message)); }

    ouverts.push(p);
    notifier();
    options.surOuverture && options.surOuverture(genre);
    return p;
  }

  return {
    ouvrir, fermer,
    fermerTout() { ouverts.slice().forEach(p => fermer(p, true)); notifier(); },
    rouvrir() { if (dernierFerme) ouvrir(dernierFerme); },
    // ne garde que les `n` plus récents (passage en mode vidéo)
    limiter(n) { while (ouverts.length > n) fermer(ouverts[0], true); notifier(); },
    get nombre() { return ouverts.length; },
    // un panneau de ce genre encore ouvert (pour l'allumer ou le rafraîchir sans en ouvrir un second)
    ouvertDeGenre(genre) { return ouverts.find(p => p.classList.contains("genre-" + genre) && !p.classList.contains("ferme")) || null; },
  };
}
