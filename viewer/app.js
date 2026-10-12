/* hedron UGP spec viewer — t_bb76d3b7. Zero dependencies: WebGL1 + fetch.
   Renders only what the emitted spec bundles contain. Geometric validity
   never implies knitability: unsupported joints are surfaced, never hidden,
   and machine_verdict=UNSIMULATED is shown as UNVERIFIED, never PASS. */
"use strict";

/* ---------- tiny vec / mat helpers ---------- */
function v3(x, y, z) { return [x, y, z]; }
function vsub(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; }
function vadd(a, b) { return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]; }
function vscale(a, s) { return [a[0] * s, a[1] * s, a[2] * s]; }
function vdot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
function vcross(a, b) {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
          a[0] * b[1] - a[1] * b[0]];
}
function vlen(a) { return Math.hypot(a[0], a[1], a[2]); }
function vnorm(a) { var l = vlen(a) || 1; return vscale(a, 1 / l); }

function mat4Identity() {
  return [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1];
}
function mat4Multiply(a, b) { /* column-major a*b */
  var out = new Array(16);
  for (var c = 0; c < 4; c++)
    for (var r = 0; r < 4; r++) {
      var s = 0;
      for (var k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k];
      out[c * 4 + r] = s;
    }
  return out;
}
function mat4Perspective(fovy, aspect, near, far) {
  var f = 1 / Math.tan(fovy / 2), nf = 1 / (near - far);
  return [f / aspect,0,0,0, 0,f,0,0, 0,0,(far + near) * nf,-1, 0,0,2 * far * near * nf,0];
}
function mat4LookAt(eye, center, up) {
  var z = vnorm(vsub(eye, center));
  var x = vnorm(vcross(up, z));
  var y = vcross(z, x);
  return [x[0],y[0],z[0],0, x[1],y[1],z[1],0, x[2],y[2],z[2],0,
          -vdot(x,eye),-vdot(y,eye),-vdot(z,eye),1];
}
function mat4Translate(x, y, z) {
  var m = mat4Identity(); m[12] = x; m[13] = y; m[14] = z; return m;
}

/* ---------- shaders ---------- */
var VS_LIT = [
  "attribute vec3 aPos; attribute vec3 aNormal;",
  "uniform mat4 uProj; uniform mat4 uView;",
  "varying vec3 vNormal; varying vec3 vPos;",
  "void main() {",
  "  vec4 world = vec4(aPos, 1.0);",
  "  gl_Position = uProj * uView * world;",
  "  vNormal = aNormal; vPos = world.xyz;",
  "}"].join("\n");
var FS_LIT = [
  "precision mediump float;",
  "varying vec3 vNormal; varying vec3 vPos;",
  "uniform vec3 uColor; uniform vec3 uEye;",
  "void main() {",
  "  vec3 n = normalize(vNormal);",
  "  if (!gl_FrontFacing) n = -n;",   /* two-sided: flat faces too */
  "  vec3 light = normalize(vec3(0.45, 0.85, 0.55));",
  "  float diff = max(dot(n, light), 0.0);",
  "  float amb = 0.36;",
  "  vec3 viewDir = normalize(uEye - vPos);",
  "  vec3 h = normalize(light + viewDir);",
  "  float spec = pow(max(dot(n, h), 0.0), 42.0) * 0.20;",
  "  gl_FragColor = vec4(uColor * (amb + diff * 0.78) + spec, 1.0);",
  "}"].join("\n");
var VS_FLAT = [
  "attribute vec3 aPos;",
  "uniform mat4 uProj; uniform mat4 uView;",
  "uniform float uPointSize;",
  "void main() {",
  "  gl_Position = uProj * uView * vec4(aPos, 1.0);",
  "  gl_PointSize = uPointSize;",
  "}"].join("\n");
var FS_FLAT = [
  "precision mediump float; uniform vec3 uColor;",
  "void main() { gl_FragColor = vec4(uColor, 1.0); }"].join("\n");

function makeProgram(gl, vsSrc, fsSrc) {
  function sh(type, src) {
    var s = gl.createShader(type);
    gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS))
      throw new Error("shader: " + gl.getShaderInfoLog(s));
    return s;
  }
  var p = gl.createProgram();
  gl.attachShader(p, sh(gl.VERTEX_SHADER, vsSrc));
  gl.attachShader(p, sh(gl.FRAGMENT_SHADER, fsSrc));
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS))
    throw new Error("link: " + gl.getProgramInfoLog(p));
  return p;
}

/* ---------- geometry from spec primitives ---------- */
var SEG_RIM = 64;      /* rim circle resolution */
var SEG_DOME_U = 32;   /* hemisphere longitude */
var SEG_DOME_V = 16;   /* hemisphere latitude */
var DISK_H = 2.0;      /* mm; disks are flat: draw a thin plate so light works */

function basisFromAxis(axis) {
  var n = vnorm(axis);
  var helper = Math.abs(n[1]) < 0.9 ? v3(0, 1, 0) : v3(1, 0, 0);
  var u = vnorm(vcross(helper, n));
  var v = vcross(n, u);
  return { n: n, u: u, v: v };
}
function ringPoint(origin, basis, radius, t, theta) {
  var dir = vadd(vscale(basis.u, Math.cos(theta)),
                 vscale(basis.v, Math.sin(theta)));
  return vadd(vadd(origin, vscale(basis.n, t)), vscale(dir, radius));
}

/* Returns {tris:{pos,nrm}, rims:[{pts, open}], bounds:{min,max}, center} */
function buildPrimMesh(prim) {
  var origin = prim.origin, axis = prim.axis || [0, 1, 0];
  var basis = basisFromAxis(axis);
  var pos = [], nrm = [], rims = [];
  function tri(a, b, c) {
    var n = vnorm(vcross(vsub(b, a), vsub(c, a)));
    pos.push(a[0],a[1],a[2], b[0],b[1],b[2], c[0],c[1],c[2]);
    nrm.push(n[0],n[1],n[2], n[0],n[1],n[2], n[0],n[1],n[2]);
  }
  var lo = v3(1e9,1e9,1e9), hi = v3(-1e9,-1e9,-1e9);
  function eat(p) {
    lo = [Math.min(lo[0],p[0]),Math.min(lo[1],p[1]),Math.min(lo[2],p[2])];
    hi = [Math.max(hi[0],p[0]),Math.max(hi[1],p[1]),Math.max(hi[2],p[2])];
  }
  var kind = prim.kind, P = prim.params || {};

  if (kind === "tube") {
    var l = P.l, r1 = P.r1, r2 = P.r2;
    var STEPS = 24;
    var slope = (r2 - r1) / l;
    var k = slope / Math.sqrt(1 + slope * slope);
    var rings = [];
    for (var i = 0; i <= STEPS; i++) {
      var t = l * i / STEPS, r = r1 + (r2 - r1) * i / STEPS;
      var ring = [];
      for (var s = 0; s < SEG_RIM; s++) {
        var th = 2 * Math.PI * s / SEG_RIM;
        var p = ringPoint(origin, basis, r, t, th);
        ring.push(p); eat(p);
        /* outward normal of a cone frustum, tilted by the slope */
        var radial = vnorm(vsub(p, vadd(origin, vscale(basis.n, t))));
        var nrmv = vnorm(vadd(radial, vscale(basis.n, -k)));
        nrm.push(nrmv[0], nrmv[1], nrmv[2]);
        pos.push(p[0], p[1], p[2]);
      }
      rings.push(ring);
    }
    function vid(ring, s) { return ring * SEG_RIM + (s % SEG_RIM); }
    for (i = 0; i < STEPS; i++)
      for (s = 0; s < SEG_RIM; s++) {
        /* two CCW triangles over the ring grid (a,b,c / a,c,d) */
        var ia = vid(i, s), ib = vid(i, s + 1),
            ic = vid(i + 1, s), idv = vid(i + 1, s + 1);
        pos.push(pos[ia*3], pos[ia*3+1], pos[ia*3+2],
                 pos[ic*3], pos[ic*3+1], pos[ic*3+2],
                 pos[ib*3], pos[ib*3+1], pos[ib*3+2]);
        nrm.push(nrm[ia*3], nrm[ia*3+1], nrm[ia*3+2],
                 nrm[ic*3], nrm[ic*3+1], nrm[ic*3+2],
                 nrm[ib*3], nrm[ib*3+1], nrm[ib*3+2]);
        pos.push(pos[ib*3], pos[ib*3+1], pos[ib*3+2],
                 pos[ic*3], pos[ic*3+1], pos[ic*3+2],
                 pos[idv*3], pos[idv*3+1], pos[idv*3+2]);
        nrm.push(nrm[ib*3], nrm[ib*3+1], nrm[ib*3+2],
                 nrm[ic*3], nrm[ic*3+1], nrm[ic*3+2],
                 nrm[idv*3], nrm[idv*3+1], nrm[idv*3+2]);
      }
    rims.push({ pts: rings[0].slice(), open: true });          /* rim_start */
    rims.push({ pts: rings[STEPS].slice(), open: true });      /* rim_end   */
  } else if (kind === "hemisphere") {
    var r = P.r;
    var face = [];
    for (s = 0; s < SEG_RIM; s++) {
      th = 2 * Math.PI * s / SEG_RIM;
      face.push(ringPoint(origin, basis, r, 0, th)); eat(face[face.length-1]);
    }
    var center = origin;
    for (s = 0; s < SEG_RIM; s++) {
      var a1 = face[s], b1 = face[(s + 1) % SEG_RIM];
      tri(a1, b1, center); /* flat face (double-sided shading fix below) */
    }
    var dome = [];
    for (var vi = 0; vi <= SEG_DOME_V; vi++) {
      var phi = (Math.PI / 2) * vi / SEG_DOME_V; /* 0=equator .. PI/2=apex */
      var row = [];
      for (s = 0; s <= SEG_DOME_U; s++) {
        th = 2 * Math.PI * s / SEG_DOME_U;
        var local = vadd(vscale(basis.u, Math.cos(th) * Math.cos(phi)),
                         vscale(basis.v, Math.sin(th) * Math.cos(phi)));
        var p2 = vadd(vadd(origin, vscale(basis.n, r * Math.sin(phi))),
                      local);
        row.push(p2); eat(p2);
      }
      dome.push(row);
    }
    for (vi = 0; vi < SEG_DOME_V; vi++)
      for (s = 0; s < SEG_DOME_U; s++) {
        var s2b = s + 1;
        tri(dome[vi][s], dome[vi][s2b], dome[vi + 1][s]);
        tri(dome[vi][s2b], dome[vi + 1][s2b], dome[vi + 1][s]);
      }
    rims.push({ pts: face.slice(), open: false }); /* sealed face rim */
  } else if (kind === "disk") {
    var rd = P.r;
    var top = [], bot = [];
    for (s = 0; s < SEG_RIM; s++) {
      th = 2 * Math.PI * s / SEG_RIM;
      var pt = ringPoint(vadd(origin, vscale(basis.n, DISK_H / 2)), basis,
                         rd, 0, th);
      var pb = ringPoint(vadd(origin, vscale(basis.n, -DISK_H / 2)), basis,
                         rd, 0, th);
      top.push(pt); bot.push(pb); eat(pt); eat(pb);
    }
    var ct = vadd(origin, vscale(basis.n, DISK_H / 2));
    var cb = vadd(origin, vscale(basis.n, -DISK_H / 2));
    for (s = 0; s < SEG_RIM; s++) {
      var s3 = (s + 1) % SEG_RIM;
      tri(top[s], top[s3], ct);
      tri(bot[s3], bot[s], cb);
      tri(top[s], bot[s], top[s3]);
      tri(bot[s], bot[s3], top[s3]);
    }
    rims.push({ pts: top.slice(), open: false });
  } else {
    /* unknown kind: draw a small marker box so the gap is visible */
    var m = 6;
    var corners = [];
    for (var dx = -1; dx <= 1; dx += 2)
      for (var dy = -1; dy <= 1; dy += 2)
        for (var dz = -1; dz <= 1; dz += 2)
          corners.push(vadd(origin, v3(dx * m, dy * m, dz * m)));
    for (i = 0; i < 12; i++) eat(corners[i]);
    var edges = [[0,1],[1,3],[3,2],[2,0],[4,5],[5,7],[7,6],[6,4],[0,4],[1,5],[2,6],[3,7]];
    var pts = edges.map(function (e) {
      return [corners[e[0]], corners[e[1]]];
    });
    return { lines: pts, rims: rims, bounds: { min: lo, max: hi },
             center: vscale(vadd(lo, hi), 0.5) };
  }

  return { pos: pos, nrm: nrm, rims: rims, bounds: { min: lo, max: hi },
           center: vscale(vadd(lo, hi), 0.5) };
}

/* ---------- WebGL setup ---------- */
function SpecViewer(canvas) {
  var gl = canvas.getContext("webgl", { antialias: true }) ||
           canvas.getContext("experimental-webgl");
  if (!gl) throw new Error("WebGL unavailable in this browser");
  this.gl = gl;
  this.canvas = canvas;
  this.progLit = makeProgram(gl, VS_LIT, FS_LIT);
  this.progFlat = makeProgram(gl, VS_FLAT, FS_FLAT);
  this.aPosLit = gl.getAttribLocation(this.progLit, "aPos");
  this.aNrmLit = gl.getAttribLocation(this.progLit, "aNormal");
  this.uProjLit = gl.getUniformLocation(this.progLit, "uProj");
  this.uViewLit = gl.getUniformLocation(this.progLit, "uView");
  this.uColorLit = gl.getUniformLocation(this.progLit, "uColor");
  this.uEyeLit = gl.getUniformLocation(this.progLit, "uEye");
  this.aPosFlat = gl.getAttribLocation(this.progFlat, "aPos");
  this.uProjFlat = gl.getUniformLocation(this.progFlat, "uProj");
  this.uViewFlat = gl.getUniformLocation(this.progFlat, "uView");
  this.uColorFlat = gl.getUniformLocation(this.progFlat, "uColor");
  this.uPtSize = gl.getUniformLocation(this.progFlat, "uPointSize");

  /* pick framebuffer: texture-backed RGBA8 (WebGL1 renderbuffers top out
     at RGBA4, which cannot distinguish enough ids) */
  this.pickFB = gl.createFramebuffer();
  this.pickTex = gl.createTexture();
  this.pickDepth = gl.createRenderbuffer();

  this.tris = [];      /* {vboPos, vboNrm, n, primIndex, color} */
  this.lines = [];     /* {vbo, n, color} */
  this.points = [];    /* {vbo, n, color} */
  this.primCenters = [];
  this.jointAnchors = [];
  this.eye = [0, 0, 5];
  this.target = [0, 0, 0];
  this.yaw = 0.6; this.pitch = 0.35; this.dist = 400;
  this.selected = -1;
  this.showLabels = true;
  this.showUnsupported = true;
  this.onpick = null;
}
SpecViewer.prototype.destroy = function () {
  var gl = this.gl;
  this.tris.concat(this.lines, this.points).forEach(function (b) {
    gl.deleteBuffer(b.vbo);
  });
  gl.deleteFramebuffer(this.pickFB);
  gl.deleteTexture(this.pickTex);
  gl.deleteRenderbuffer(this.pickDepth);
};
SpecViewer.prototype._buf = function (data) {
  var gl = this.gl, vbo = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(data), gl.STATIC_DRAW);
  return vbo;
};
SpecViewer.prototype.loadGraph = function (graph, unsupportedJointIds) {
  var gl = this.gl, self = this;
  this.tris.forEach(function (b) { gl.deleteBuffer(b.vboPos); gl.deleteBuffer(b.vboNrm); });
  this.lines.forEach(function (b) { gl.deleteBuffer(b.vbo); });
  this.points.forEach(function (b) { gl.deleteBuffer(b.vbo); });
  this.tris = []; this.lines = []; this.points = [];
  this.primCenters = [];
  var loAll = v3(1e9,1e9,1e9), hiAll = v3(-1e9,-1e9,-1e9);

  graph.primitives.forEach(function (prim, idx) {
    var mesh;
    try { mesh = buildPrimMesh(prim); }
    catch (err) {
      mesh = { lines: [], rims: [], bounds: { min: prim.origin, max: prim.origin },
               center: prim.origin, pos: [], nrm: [] };
    }
    self.primCenters.push(mesh.center);
    [mesh.bounds.min, mesh.bounds.max].forEach(function (p) {
      loAll = [Math.min(loAll[0],p[0]),Math.min(loAll[1],p[1]),Math.min(loAll[2],p[2])];
      hiAll = [Math.max(hiAll[0],p[0]),Math.max(hiAll[1],p[1]),Math.max(hiAll[2],p[2])];
    });
    if (mesh.pos && mesh.pos.length) {
      self.tris.push({
        vboPos: self._buf(mesh.pos), vboNrm: self._buf(mesh.nrm),
        n: mesh.pos.length / 3, primIndex: idx
      });
    }
    (mesh.rims || []).forEach(function (rim) {
      var flat = [];
      rim.pts.forEach(function (p, i) {
        flat.push(p[0], p[1], p[2]);
        if (i) flat.push(p[0], p[1], p[2]);
      });
      flat.push(rim.pts[0][0], rim.pts[0][1], rim.pts[0][2]);
      self.lines.push({ vbo: self._buf(flat), n: flat.length / 3,
                        color: rim.open ? [0.16, 0.42, 0.66]   /* open rim */
                                        : [0.45, 0.52, 0.60],  /* sealed  */
                        primIndex: idx });
    });
    if (mesh.lines) mesh.lines.forEach(function (seg) {
      self.lines.push({ vbo: self._buf([seg[0][0],seg[0][1],seg[0][2],
                                        seg[1][0],seg[1][1],seg[1][2]]),
                        n: 2, color: [0.66, 0.45, 0.16], primIndex: idx });
    });
  });

  /* joint anchors: unsupported ones get their own marker set */
  var jj = graph.joints || {};
  var allJ = [].concat(jj.rim_joints || [], jj.surface_branches || [],
                       jj.terminus_continuations || []);
  this.jointAnchors = allJ.map(function (j) {
    return { id: j.id, construction: j.construction,
             unsupported: unsupportedJointIds.indexOf(j.id) >= 0,
             point: (j.anchor && j.anchor.point) || null,
             parent: j.parent, child: j.child };
  }).filter(function (j) { return !!j.point; });

  /* one static VBO for the unsupported-joint markers */
  if (this.unsupBuf) gl.deleteBuffer(this.unsupBuf);
  var unsupPts = [];
  this.jointAnchors.forEach(function (j) {
    if (j.unsupported) unsupPts.push(j.point[0], j.point[1], j.point[2]);
  });
  this.unsupBuf = unsupPts.length ? this._buf(unsupPts) : null;
  this.unsupCount = unsupPts.length / 3;

  /* camera fit */
  var ctr = vscale(vadd(loAll, hiAll), 0.5);
  var radius = Math.max(vlen(vsub(hiAll, loAll)) / 2, 10);
  this.target = ctr;
  this.dist = radius * 2.4;
  this.homeDist = this.dist;
};
SpecViewer.prototype._resizePick = function (w, h) {
  var gl = this.gl;
  gl.bindFramebuffer(gl.FRAMEBUFFER, this.pickFB);
  gl.bindTexture(gl.TEXTURE_2D, this.pickTex);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA,
                gl.UNSIGNED_BYTE, null);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0,
                          gl.TEXTURE_2D, this.pickTex, 0);
  gl.bindRenderbuffer(gl.RENDERBUFFER, this.pickDepth);
  gl.renderbufferStorage(gl.RENDERBUFFER, gl.DEPTH_COMPONENT16, w, h);
  gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT,
                             gl.RENDERBUFFER, this.pickDepth);
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
};
SpecViewer.prototype._matrices = function () {
  var eye = [
    this.target[0] + this.dist * Math.cos(this.pitch) * Math.sin(this.yaw),
    this.target[1] + this.dist * Math.sin(this.pitch),
    this.target[2] + this.dist * Math.cos(this.pitch) * Math.cos(this.yaw)];
  this.eye = eye;
  var aspect = this.canvas.width / Math.max(this.canvas.height, 1);
  var proj = mat4Perspective(0.7, aspect, this.dist / 100, this.dist * 12);
  var view = mat4LookAt(eye, this.target, [0, 1, 0]);
  return { proj: proj, view: view };
};
SpecViewer.prototype._draw = function (proj, view, mode) {
  /* mode: "color" | "pick" */
  var gl = this.gl;
  gl.enable(gl.DEPTH_TEST);
  gl.clearColor(0, 0, 0, 0);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  if (mode === "pick") {
    gl.useProgram(this.progFlat);
    gl.uniformMatrix4fv(this.uProjFlat, false, proj);
    gl.uniformMatrix4fv(this.uViewFlat, false, view);
    gl.uniform1f(this.uPtSize, 1);
    this.tris.forEach(function (b) {
      var id = b.primIndex + 1;
      gl.uniform3f(this.uColorFlat,
                   ((id >> 0) & 255) / 255, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, b.vboPos);
      gl.enableVertexAttribArray(this.aPosFlat);
      gl.vertexAttribPointer(this.aPosFlat, 3, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.TRIANGLES, 0, b.n);
    }, this);
  } else {
    gl.useProgram(this.progLit);
    gl.uniformMatrix4fv(this.uProjLit, false, proj);
    gl.uniformMatrix4fv(this.uViewLit, false, view);
    gl.uniform3fv(this.uEyeLit, this.eye);
    this.tris.forEach(function (b) {
      var sel = b.primIndex === this.selected;
      var base = PRIM_COLORS[b.primIndex % PRIM_COLORS.length];
      var col = sel ? [0.95, 0.62, 0.18] : base;
      gl.uniform3fv(this.uColorLit, col);
      gl.bindBuffer(gl.ARRAY_BUFFER, b.vboPos);
      gl.enableVertexAttribArray(this.aPosLit);
      gl.vertexAttribPointer(this.aPosLit, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, b.vboNrm);
      gl.enableVertexAttribArray(this.aNrmLit);
      gl.vertexAttribPointer(this.aNrmLit, 3, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.TRIANGLES, 0, b.n);
    }, this);
    gl.useProgram(this.progFlat);
    gl.uniformMatrix4fv(this.uProjFlat, false, proj);
    gl.uniformMatrix4fv(this.uViewFlat, false, view);
    gl.uniform1f(this.uPtSize, 1);
    this.lines.forEach(function (b) {
      var sel = b.primIndex === this.selected;
      gl.uniform3f(this.uColorFlat,
                   sel ? 0.95 : b.color[0], sel ? 0.62 : b.color[1],
                   sel ? 0.18 : b.color[2]);
      gl.bindBuffer(gl.ARRAY_BUFFER, b.vbo);
      gl.enableVertexAttribArray(this.aPosFlat);
      gl.vertexAttribPointer(this.aPosFlat, 3, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.LINES, 0, b.n);
    }, this);
    if (this.showUnsupported) {
      var unsup = this.jointAnchors.filter(function (j) { return j.unsupported; });
      if (unsup.length && this.unsupBuf) {
        gl.uniform3f(this.uColorFlat, 0.86, 0.55, 0.10);
        gl.uniform1f(this.uPtSize, 9);
        gl.bindBuffer(gl.ARRAY_BUFFER, this.unsupBuf);
        gl.enableVertexAttribArray(this.aPosFlat);
        gl.vertexAttribPointer(this.aPosFlat, 3, gl.FLOAT, false, 0, 0);
        gl.drawArrays(gl.POINTS, 0, this.unsupCount);
        gl.uniform1f(this.uPtSize, 1);
      }
    }
  }
};
SpecViewer.prototype.render = function () {
  var gl = this.gl, c = this.canvas;
  var dpr = Math.min(window.devicePixelRatio || 1, 2);
  var w = Math.floor(c.clientWidth * dpr), h = Math.floor(c.clientHeight * dpr);
  if (c.width !== w || c.height !== h) {
    c.width = w; c.height = h;
    this._resizePick(w, h);
  }
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  gl.viewport(0, 0, c.width, c.height);
  gl.enable(gl.DEPTH_TEST);
  var m = this._matrices();
  gl.clearColor(0, 0, 0, 0);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  this._draw(m.proj, m.view, "color");
  return m;
};
SpecViewer.prototype.pick = function (x, y) {
  var gl = this.gl, c = this.canvas;
  var m = this._matrices();
  gl.bindFramebuffer(gl.FRAMEBUFFER, this.pickFB);
  gl.viewport(0, 0, c.width, c.height);
  this._draw(m.proj, m.view, "pick");
  var px = Math.floor(x * c.width), py = Math.floor((1 - y) * c.height);
  var pix = new Uint8Array(4);
  gl.readPixels(px, py, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pix);
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  return pix[0] - 1; /* primIndex or -1 */
};
SpecViewer.prototype.project = function (p, m) {
  var v = [p[0], p[1], p[2], 1];
  function mul(mat, vec) {
    var o = [0,0,0,0];
    for (var c = 0; c < 4; c++)
      for (var k = 0; k < 4; k++) o[c] += mat[c * 4 + k] * vec[k];
    return o;
  }
  var vp = mul(m.proj, mul(m.view, v));
  if (vp[3] === 0) return null;
  return { x: (vp[0] / vp[3] + 1) / 2, y: (1 - vp[1] / vp[3]) / 2,
           w: vp[3] };
};

var PRIM_COLORS = [
  [0.36, 0.58, 0.78], [0.55, 0.72, 0.60], [0.72, 0.62, 0.78],
  [0.78, 0.68, 0.45], [0.50, 0.70, 0.72], [0.68, 0.55, 0.50],
  [0.58, 0.62, 0.80], [0.62, 0.74, 0.55], [0.76, 0.60, 0.68],
  [0.55, 0.66, 0.60]
];

/* ---------- app state / DOM ---------- */
var FAMILIES = ["dress", "glove", "hat", "hoodie", "shirt", "shorts",
                "skirt", "sock", "trousers"];
var state = {
  bundles: {},          /* family -> bundle or {error} */
  current: null,
  viewer: null,
  labels: {},           /* family-agnostic label divs, rebuilt per family */
};

function $(id) { return document.getElementById(id); }

function el(tag, cls, text) {
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}
function chip(text, cls) {
  var c = el("span", "chip" + (cls ? " " + cls : ""), text);
  return c;
}
function kv(k, v) {
  var row = el("div", "kv");
  row.appendChild(el("span", "k", k));
  row.appendChild(el("span", "v", String(v)));
  return row;
}
function fmtN(n) {
  if (n === null || n === undefined) return "—";
  if (typeof n !== "number") return String(n);
  return (Math.round(n * 100) / 100).toString();
}

function statusDot(bundle) {
  if (!bundle || bundle.error) return "missing";
  var val = bundle.validation, bb = bundle.buildability.default_knit;
  if (!val.ok || bb.geometric_validity === "FAIL") return "fail";
  var statuses = Object.keys(bb.per_class || {})
    .map(function (k) { return bb.per_class[k]; });
  if (statuses.indexOf("FAIL") >= 0) return "fail";
  if (statuses.indexOf("UNVERIFIED") >= 0) return "unverified";
  return "pass";
}

function showOverlay(title, bodyBuilder, detail) {
  $("ov-title").textContent = title;
  var body = $("ov-body");
  body.textContent = "";
  bodyBuilder(body);
  $("ov-detail").textContent = detail || "";
  $("overlay").style.display = "flex";
}

function hideOverlay() { $("overlay").style.display = "none"; }

function fetchBundle(fam) {
  return fetch("../out/" + fam + ".json").then(function (resp) {
    if (!resp.ok) throw new Error("HTTP " + resp.status + " for out/" +
                                  fam + ".json");
    return resp.json();
  });
}

function loadAll() {
  return Promise.all(FAMILIES.map(function (fam) {
    return fetchBundle(fam).then(
      function (b) { state.bundles[fam] = b; },
      function (err) { state.bundles[fam] = { error: String(err) }; });
  }));
}

/* ---------- rail ---------- */
function renderRail() {
  var wrap = $("fambtns");
  wrap.textContent = "";
  FAMILIES.forEach(function (fam) {
    var b = state.bundles[fam];
    var btn = el("button", "fambtn");
    var dot = el("span", "dot " + statusDot(b));
    btn.appendChild(dot);
    btn.appendChild(el("span", "fam", fam));
    if (b && !b.error) {
      btn.appendChild(el("span", "pieces",
        String(b.plan.stats.piece_count) + "p"));
    }
    btn.addEventListener("click", function () { selectFamily(fam); });
    wrap.appendChild(btn);
  });
  /* legend */
  var lg = $("legend");
  lg.textContent = "";
  [["#2f7d4f", "PASS — well-formed per the catalog"],
   ["#a8730f", "UNVERIFIED — needs a gauge / machine sim"],
   ["#b3372e", "FAIL — invariant violated"],
   ["rgba(0,0,0,0)", "hollow: bundle missing (run emit_specs.py)"]
  ].forEach(function (row) {
    var r = el("div", "row");
    var sw = el("span", "swatch");
    if (row[0] === "rgba(0,0,0,0)") {
      sw.style.background = "transparent";
      sw.style.border = "1.5px dashed #b3372e";
    } else sw.style.background = row[0];
    r.appendChild(sw);
    r.appendChild(el("span", null, row[1]));
    lg.appendChild(r);
  });
}

/* ---------- right panel ---------- */
function renderPanel(fam) {
  var panel = $("panel");
  panel.textContent = "";
  var b = state.bundles[fam];
  if (!b || b.error) {
    var c0 = el("div", "card");
    c0.appendChild(el("h3", null, "Bundle unavailable"));
    c0.appendChild(el("p", null, b && b.error ? b.error :
      "out/" + fam + ".json could not be loaded."));
    panel.appendChild(c0);
    return;
  }
  var g = b.graph;
  var nPrims = g.primitives.length;
  var joints = [].concat(g.joints.rim_joints, g.joints.surface_branches,
                         g.joints.terminus_continuations);

  /* spec summary */
  var cs = el("div", "card");
  cs.appendChild(el("h3", null, "Spec — " + fam));
  cs.appendChild(kv("family / scale", b.family + " @ " + b.scale));
  cs.appendChild(kv("emitted at version", b.emitted_at_version));
  cs.appendChild(kv("graph version", g.version));
  cs.appendChild(kv("primitives", nPrims));
  cs.appendChild(kv("joints", joints.length +
    " (" + g.joints.rim_joints.length + " rim, " +
    g.joints.surface_branches.length + " surface, " +
    g.joints.terminus_continuations.length + " terminus)"));
  cs.appendChild(kv("graph ops", g.ops.length));
  cs.appendChild(kv("open boundaries", g.open_boundaries.length));
  cs.appendChild(kv("gauge", g.gauge ?
    g.gauge.wale_mm + " mm wale / " + g.gauge.course_mm + " mm course" : "—"));
  var unsupported = g.joints.surface_branches.filter(function (j) {
    return j.construction === "unsupported";
  });
  if (unsupported.length) {
    var urow = el("div", "kv");
    urow.appendChild(el("span", "k", "unsupported"));
    var uwrap = el("span", "chips");
    unsupported.forEach(function (j) {
      uwrap.appendChild(chip(j.child, "unsupported"));
    });
    urow.appendChild(uwrap);
    cs.appendChild(urow);
  }
  panel.appendChild(cs);

  /* validation */
  var cv = el("div", "card");
  cv.appendChild(el("h3", null, "Validation"));
  var head = el("div", "kv");
  head.appendChild(el("span", "k", "result"));
  var okch = b.validation.ok ? chip("ok", "pass") : chip("FAILED", "fail");
  okch.classList.add("pr-status");
  head.appendChild(okch);
  cv.appendChild(head);
  var tbl = el("table", "findings");
  var thead = el("tr");
  ["invariant", "subject", "status"].forEach(function (h) {
    var th = el("th", null, h); thead.appendChild(th);
  });
  tbl.appendChild(thead);
  b.validation.findings.forEach(function (f) {
    var tr = el("tr");
    tr.appendChild(el("td", "mono", f.invariant));
    tr.appendChild(el("td", "mono", f.subject));
    var td = el("td", "st-" + f.status, f.status);
    tr.appendChild(td);
    if (f.message) tr.title = f.message;
    tbl.appendChild(tr);
  });
  cv.appendChild(tbl);
  panel.appendChild(cv);

  /* buildability */
  var bb = b.buildability.default_knit;
  var cb = el("div", "card");
  cb.appendChild(el("h3", null, "Buildability — " + bb.backend));
  var brow = el("div", "kv");
  brow.appendChild(el("span", "k", "geometric validity"));
  brow.appendChild(chip(bb.geometric_validity,
    bb.geometric_validity === "PASS" ? "pass" :
    bb.geometric_validity === "FAIL" ? "fail" : "unverified"));
  cb.appendChild(brow);
  if (bb.note) {
    var note = el("div", "note", bb.note);
    cb.appendChild(note);
  }
  var grid = el("div", "classgrid");
  Object.keys(bb.per_class).sort().forEach(function (k) {
    var cell = el("div", "cg");
    cell.appendChild(el("span", null, k));
    var st = bb.per_class[k];
    cell.appendChild(el("span", "st-" + st, st));
    grid.appendChild(cell);
  });
  cb.appendChild(grid);
  if (bb.failing_instances && bb.failing_instances.length) {
    cb.appendChild(el("div", "note unsupported-note",
      "failing instances: " + JSON.stringify(bb.failing_instances)));
  }
  panel.appendChild(cb);

  /* machine plan */
  var st = b.plan.stats;
  var cp = el("div", "card");
  cp.appendChild(el("h3", null, "Machine plan"));
  var prow = el("div", "kv");
  prow.appendChild(el("span", "k", "machine verdict"));
  prow.appendChild(chip(st.machine_verdict,
    st.machine_verdict === "SIMULATED" ? "pass" : "unverified"));
  cp.appendChild(prow);
  cp.appendChild(kv("pieces", st.piece_count));
  cp.appendChild(kv("joints", st.joint_count));
  var verbs = Object.keys(st.machine_ops_by_verb).sort()
    .map(function (k) { return k + "×" + st.machine_ops_by_verb[k]; })
    .join(", ");
  cp.appendChild(kv("machine verbs", verbs || "—"));
  var kinds = Object.keys(st.ops_by_kind).sort()
    .map(function (k) { return k + "×" + st.ops_by_kind[k]; }).join(", ");
  cp.appendChild(kv("graph ops", kinds || "—"));
  if (st.open_boundaries.length) {
    cp.appendChild(kv("open at end", st.open_boundaries.join(", ")));
  }
  (b.plan.notes || []).forEach(function (n) {
    cp.appendChild(el("div", "note unsupported-note", n));
  });
  panel.appendChild(cp);

  /* primitives + boundaries */
  var cpr = el("div", "card");
  cpr.appendChild(el("h3", null, "Primitives"));
  g.primitives.forEach(function (p, idx) {
    var row = el("div", "primrow");
    row.dataset.prim = idx;
    var hd = el("div", "pr-head");
    hd.appendChild(el("span", "pr-id", p.id));
    hd.appendChild(el("span", "pr-kind", p.kind));
    row.appendChild(hd);
    var sub = el("div", "pr-sub");
    var bits = [];
    Object.keys(p.params).forEach(function (k) {
      bits.push(k + " " + fmtN(p.params[k]) + " mm");
    });
    sub.textContent = bits.join(" · ");
    row.appendChild(sub);
    var bnd = el("div", "pr-bnd");
    (b.boundaries[p.id] || []).forEach(function (r) {
      var line = el("div");
      line.appendChild(el("span", r.kind === "inert" ? "inert" : null,
        r.boundary + " (" + r.kind + ") " + fmtN(r.length_mm) + " mm" +
        (r.loops === null ? "" : " · " + r.loops + " loops")));
      bnd.appendChild(line);
    });
    row.appendChild(bnd);
    row.addEventListener("click", function () {
      selectPrim(idx);
    });
    cpr.appendChild(row);
  });
  panel.appendChild(cpr);

  /* joints */
  var cj = el("div", "card");
  cj.appendChild(el("h3", null, "Joints"));
  joints.forEach(function (j) {
    var row = el("div", "primrow");
    var hd = el("div", "pr-head");
    hd.appendChild(el("span", "pr-id", j.id));
    var cls = j.construction === "unsupported" ? "unsupported" : "renderonly";
    var jc = chip(j.construction, cls);
    hd.appendChild(jc);
    row.appendChild(hd);
    var sub = el("div", "pr-sub",
      j.parent + " → " + j.child +
      (j.realized_by && j.realized_by.length ?
        " · realized_by " + j.realized_by.join(", ") : ""));
    row.appendChild(sub);
    cj.appendChild(row);
  });
  panel.appendChild(cj);

  panel.appendChild(el("div", "footnote",
    "Everything above is read from out/" + fam + ".json — emitted by " +
    "tools/emit_specs.py from the library. PASS = well-formed geometry " +
    "per the invariant catalog; geometric validity never implies " +
    "knitability."));
}

/* ---------- labels overlay ---------- */
function rebuildLabels() {
  var wrap = $("labels");
  wrap.textContent = "";
  state.labels = {};
  var b = state.bundles[state.current];
  if (!b || b.error) return;
  var g = b.graph;
  var viewer = state.viewer;
  g.primitives.forEach(function (p, idx) {
    var lab = el("div", "plabel", p.id);
    wrap.appendChild(lab);
    state.labels["p" + idx] = lab;
  });
  viewer.jointAnchors.forEach(function (j) {
    var lab = el("div", "plabel" + (j.unsupported ? " unsupported" : ""),
                 j.unsupported ? "✖ " + j.construction : j.construction);
    lab.style.display = j.unsupported && viewer.showUnsupported ? "" : "none";
    wrap.appendChild(lab);
    state.labels["j:" + j.id] = lab;
  });
}
function updateLabels(m) {
  var viewer = state.viewer;
  var b = state.bundles[state.current];
  var show = viewer.showLabels;
  var canvas = viewer.canvas;
  viewer.primCenters.forEach(function (ctr, idx) {
    var lab = state.labels["p" + idx];
    if (!lab) return;
    var pr = viewer.project(ctr, m);
    if (!pr || pr.w <= 0 || !show) { lab.style.display = "none"; return; }
    lab.style.display = "";
    lab.style.left = (pr.x * canvas.clientWidth) + "px";
    lab.style.top = (pr.y * canvas.clientHeight) + "px";
    lab.classList.toggle("selected", idx === viewer.selected);
  });
  viewer.jointAnchors.forEach(function (j) {
    var lab = state.labels["j:" + j.id];
    if (!lab) return;
    var pr = viewer.project(j.point, m);
    if (!pr || pr.w <= 0 || !show ||
        (j.unsupported && !viewer.showUnsupported)) {
      lab.style.display = "none"; return;
    }
    lab.style.display = "";
    lab.style.left = (pr.x * canvas.clientWidth) + "px";
    lab.style.top = (pr.y * canvas.clientHeight - 12) + "px";
  });
}

/* ---------- selection / camera ---------- */
function selectPrim(idx) {
  state.viewer.selected = idx;
  renderPanel(state.current);
  rebuildLabels();
  var rows = document.querySelectorAll("#panel .primrow[data-prim]");
  rows.forEach(function (r) {
    r.classList.toggle("selected", Number(r.dataset.prim) === idx);
  });
}
function selectFamily(fam) {
  state.current = fam;
  var btns = document.querySelectorAll(".fambtn");
  FAMILIES.forEach(function (f, i) {
    btns[i].classList.toggle("active", f === fam);
  });
  var b = state.bundles[fam];
  $("stagemsg").textContent = "";
  if (!b || b.error) {
    state.viewer.tris = []; state.viewer.lines = []; state.viewer.points = [];
    state.viewer.primCenters = []; state.viewer.jointAnchors = [];
    rebuildLabels();
    renderPanel(fam);
    $("stagemsg").textContent = "no bundle for " + fam +
      " — run tools/emit_specs.py";
    return;
  }
  var unsupportedIds = b.graph.joints.surface_branches
    .filter(function (j) { return j.construction === "unsupported"; })
    .map(function (j) { return j.id; });
  state.viewer.selected = -1;
  state.viewer.loadGraph(b.graph, unsupportedIds);
  renderPanel(fam);
  rebuildLabels();
}

/* ---------- interaction ---------- */
function wireInteraction() {
  var canvas = $("glcanvas");
  var viewer = state.viewer;
  var dragging = false, panning = false, lastX = 0, lastY = 0, moved = 0;

  canvas.addEventListener("mousedown", function (e) {
    dragging = !e.shiftKey;
    panning = e.shiftKey || e.button === 2;
    lastX = e.clientX; lastY = e.clientY; moved = 0;
    canvas.classList.add("dragging");
  });
  window.addEventListener("mouseup", function (e) {
    if (dragging && moved < 4) {
      var rect = canvas.getBoundingClientRect();
      var idx = viewer.pick(
        (e.clientX - rect.left) / rect.width,
        (e.clientY - rect.top) / rect.height);
      if (idx >= 0) selectPrim(idx);
    }
    dragging = false; panning = false;
    canvas.classList.remove("dragging");
  });
  window.addEventListener("mousemove", function (e) {
    if (dragging || panning) {
      var dx = e.clientX - lastX, dy = e.clientY - lastY;
      lastX = e.clientX; lastY = e.clientY;
      moved += Math.abs(dx) + Math.abs(dy);
      if (panning) {
        var s = state.viewer.dist / 900;
        var right = [Math.cos(state.viewer.yaw), 0,
                     -Math.sin(state.viewer.yaw)];
        state.viewer.target = vadd(state.viewer.target,
          vadd(vscale(right, -dx * s), [0, dy * s, 0]));
      } else {
        state.viewer.yaw += dx * 0.008;
        state.viewer.pitch = Math.max(-1.4, Math.min(1.4,
          state.viewer.pitch + dy * 0.008));
      }
    } else {
      hoverPick(e);
    }
  });
  canvas.addEventListener("contextmenu", function (e) {
    e.preventDefault();
  });
  canvas.addEventListener("wheel", function (e) {
    e.preventDefault();
    var f = Math.exp(e.deltaY * 0.0012);
    state.viewer.dist = Math.max(state.viewer.homeDist * 0.25,
      Math.min(state.viewer.homeDist * 4, state.viewer.dist * f));
  }, { passive: false });
  /* touch: one-finger orbit, two-finger pinch */
  var touchDist = 0;
  canvas.addEventListener("touchstart", function (e) {
    if (e.touches.length === 2) {
      touchDist = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY);
    }
  }, { passive: true });
  canvas.addEventListener("touchmove", function (e) {
    e.preventDefault();
    if (e.touches.length === 1) {
      var t = e.touches[0];
      state.viewer.yaw += (t.clientX - lastX) * 0.008;
      state.viewer.pitch = Math.max(-1.4, Math.min(1.4,
        state.viewer.pitch + (t.clientY - lastY) * 0.008));
      lastX = t.clientX; lastY = t.clientY;
    } else if (e.touches.length === 2 && touchDist) {
      var d = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY);
      state.viewer.dist *= touchDist / d;
      touchDist = d;
    }
  }, { passive: false });

  /* hover tooltip (throttled to one pick per frame) */
  var hoverPending = null;
  function hoverPick(e) {
    hoverPending = e;
  }
  function processHover() {
    if (hoverPending && state.current) {
      var e = hoverPending; hoverPending = null;
      var rect = canvas.getBoundingClientRect();
      if (e.clientX < rect.left || e.clientX > rect.right ||
          e.clientY < rect.top || e.clientY > rect.bottom) return;
      var idx = viewer.pick(
        (e.clientX - rect.left) / rect.width,
        (e.clientY - rect.top) / rect.height);
      var tt = $("tooltip");
      if (idx >= 0) {
        var b = state.bundles[state.current];
        var p = b && b.graph && b.graph.primitives && b.graph.primitives[idx];
        if (!p) { tt.style.display = "none"; }
        else {
        tt.querySelector(".tt-id").textContent = p.id;
        tt.querySelector(".tt-kind").textContent =
          p.kind + " · " + Object.keys(p.params)
            .map(function (k) { return k + " " + fmtN(p.params[k]); })
            .join(" ");
        tt.style.display = "block";
        tt.style.left = (e.clientX - rect.left + 14) + "px";
        tt.style.top = (e.clientY - rect.top + 10) + "px";
        }
      } else tt.style.display = "none";
    }
    requestAnimationFrame(processHover);
  }
  requestAnimationFrame(processHover);

  $("tgl-labels").addEventListener("change", function (e) {
    viewer.showLabels = e.target.checked;
  });
  $("tgl-unsup").addEventListener("change", function (e) {
    viewer.showUnsupported = e.target.checked;
    rebuildLabels();
  });
}

/* ---------- main loop ---------- */
function frame() {
  var viewer = state.viewer;
  if (viewer) {
    var m = viewer.render();
    updateLabels(m);
  }
  requestAnimationFrame(frame);
}

function boot() {
  var canvas = $("glcanvas");
  try {
    state.viewer = new SpecViewer(canvas);
  } catch (err) {
    showOverlay("WebGL unavailable", function (body) {
      body.appendChild(el("p", null,
        "This viewer needs WebGL; your browser refused the context."));
      body.appendChild(el("p", null, String(err)));
    }, null);
    return;
  }
  wireInteraction();
  requestAnimationFrame(frame);
  loadAll().then(function () {
    renderRail();
    var firstOk = FAMILIES.filter(function (f) {
      return state.bundles[f] && !state.bundles[f].error;
    });
    if (!firstOk.length) {
      var missing = state.bundles[FAMILIES[0]];
      showOverlay("Spec data unavailable", function (body) {
        body.appendChild(el("p", null,
          "No out/<family>.json bundles are served next to this page. " +
          "Emit them from the repo, then serve the repo root:"));
        var cmd = el("code", "cmd",
          "python3 tools/emit_specs.py\npython3 -m ugc.cli serve");
        body.appendChild(cmd);
        body.appendChild(el("p", null,
          "The page renders only what the emitted spec JSONs contain — " +
          "no bundled copy, no fabricated geometry."));
      }, missing && missing.error ? missing.error : "");
      return;
    }
    hideOverlay();
    selectFamily(firstOk.indexOf("shirt") >= 0 ? "shirt" : firstOk[0]);
  }, function (err) {
    showOverlay("Load failed", function (body) {
      body.appendChild(el("p", null, String(err)));
    }, null);
  });
}

document.addEventListener("DOMContentLoaded", boot);
