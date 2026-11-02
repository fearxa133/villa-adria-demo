// Dev-only: open the site with ?export&nomerge, then call __exportFlat() to get the flat's geometry as a .glb for Blender (tools/bake/bake.py).
// Every mesh is written in flat-local coordinates, its material named M<index into BAKE.mats>, with userData.kind / soft for the bake script.
window.__exportFlat = function () {
  const { flat, BAKE, spotPts, lights } = window.__flatExport;
  flat.updateMatrixWorld(true);
  const inv = new THREE.Matrix4().copy(flat.matrixWorld).invert(), root = new THREE.Group(), proxy = [];
  const prox = i => proxy[i] || (proxy[i] = (() => {
    const m = BAKE.mats[i], p = new THREE.MeshStandardMaterial({ name: 'M' + i, color: m.color, map: m.map || null, roughness: m.roughness ?? 1, metalness: m.metalness ?? 0 });
    if (m.emissive) p.emissive = m.emissive.clone();
    if (m.transparent) { p.transparent = true; p.opacity = m.opacity; }
    return p;
  })());
  flat.traverse(o => {
    if (!o.isMesh || !o.userData.kind) return;
    const g = o.geometry.clone(); g.applyMatrix4(new THREE.Matrix4().multiplyMatrices(inv, o.matrixWorld));
    const ms = [].concat(o.material), n = new THREE.Mesh(g, Array.isArray(o.material) ? ms.map(m => prox(BAKE.mats.indexOf(m))) : prox(BAKE.mats.indexOf(o.material)));
    if (n.material) [].concat(n.material).forEach(x => { if (!x.userData.lin) { x.color.convertSRGBToLinear(); x.emissive.convertSRGBToLinear(); x.userData.lin = 1; } });   // glTF factors are linear
    n.userData = { kind: o.userData.kind, soft: o.userData.soft ? 1 : 0, col: '#' + ms[0].color.getHexString() };
    root.add(n);
  });
  root.userData = { spots: spotPts, lights: lights.map(l => [l.position.x, l.position.y, l.position.z, '#' + l.color.getHexString()]) };
  return new Promise(res => new THREE.GLTFExporter().parse(root, async glb => {
    const r = await fetch('tools/bake/_save.php', { method: 'POST', body: glb });
    res(await r.text() + ' ' + glb.byteLength + ' bytes, ' + root.children.length + ' meshes, ' + proxy.filter(Boolean).length + ' materials');
  }, { binary: true, maxTextureSize: 1024 }));
};
