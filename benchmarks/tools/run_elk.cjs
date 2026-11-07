// ELK baseline runner: elkjs layered x single file -> raw JSON.
// Input: <graph>.elk.json ({children:[{id,width,height}], edges:[{id,sources,targets}]})
// Output: <graph>.elk.json.out (eval JSON appending is done on the python side; this process only produces native layouts)
// Usage: node run_elk.mjs <in.json> <out.layout.json>
const ELK = require(process.env.ELKJS_PATH || "elkjs/lib/elk.bundled.js");
const fs = require("fs");

const elk = new ELK();
const input = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const t0 = Date.now();
elk.layout(input, {
  layoutOptions: {
    "elk.algorithm": "layered",
    "elk.edgeRouting": "SPLINE_ARITY",
    "elk.spacing.nodeNode": "40",
    "elk.spacing.edgeEdge": "12",
  },
}).then((g) => {
  const dt = (Date.now() - t0) / 1000;
  const nodes = {};
  const walk = (n, dx, dy) => {
    const x = (n.x || 0) + dx, y = (n.y || 0) + dy;
    if (n.width && n.height && n.id && !n.children) {
      nodes[n.id] = { x: x + n.width / 2, y: y + n.height / 2, w: n.width, h: n.height };
    }
    (n.children || []).forEach((c) => walk(c, x, y));
    (n.edges || []).forEach((e) => {
      e._abs = true;
    });
  };
  walk(g, 0, 0);
  const routes = {};
  const edgeList = [];
  const collectEdges = (n, dx, dy) => {
    const ox = (n.x || 0) + dx, oy = (n.y || 0) + dy;
    (n.edges || []).forEach((e, i) => {
      const s = e.sections && e.sections[0];
      if (!s) return;
      const pts = [[s.startPoint.x + ox, s.startPoint.y + oy]]
        .concat((s.bendPoints || []).map((p) => [p.x + ox, p.y + oy]))
        .concat([[s.endPoint.x + ox, s.endPoint.y + oy]]);
      routes[edgeList.length] = pts;
      edgeList.push({ a: e.sources[0], b: e.targets[0] });
    });
    (n.children || []).forEach((c) => collectEdges(c, ox, oy));
  };
  collectEdges(g, 0, 0);
  fs.writeFileSync(process.argv[3], JSON.stringify({
    runtime_s: dt, nodes, routes, edges: edgeList,
  }, null, 1));
}).catch((e) => {
  fs.writeFileSync(process.argv[3], JSON.stringify({ status: "error", why: String(e) }));
  process.exit(1);
});
