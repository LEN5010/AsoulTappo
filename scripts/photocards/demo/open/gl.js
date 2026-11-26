// A thin layer over WebGL 2: programs, grids, textures and the few matrices the scene needs.
// The world is in design units: x right, y down, z toward the viewer, the origin in the middle of the stage.
export const DIST = 1500;

export function context(canvas) {
  const gl = canvas.getContext("webgl2", { antialias: true, alpha: false });
  if (!gl) throw new Error("no webgl2");
  gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
  return gl;
}

export function program(gl, vs, fs) {
  const compile = (type, src) => {
    const s = gl.createShader(type);
    gl.shaderSource(s, `#version 300 es\nprecision highp float;\n${src}`);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      const log = gl.getShaderInfoLog(s);
      throw new Error(log);
    }
    return s;
  };
  const prog = gl.createProgram();
  gl.attachShader(prog, compile(gl.VERTEX_SHADER, vs));
  gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, fs));
  gl.bindAttribLocation(prog, 0, "a");
  gl.bindAttribLocation(prog, 1, "b");
  gl.bindAttribLocation(prog, 2, "c");
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
  const locs = new Map();
  const loc = (n) => {
    if (!locs.has(n)) locs.set(n, gl.getUniformLocation(prog, n));
    return locs.get(n);
  };
  return {
    use: () => gl.useProgram(prog),
    set(values) {
      for (const n in values) {
        const v = values[n], l = loc(n);
        if (l === null) continue;
        if (typeof v === "number") gl.uniform1f(l, v);
        else if (v.length === 16) gl.uniformMatrix4fv(l, false, v);
        else if (v.length === 2) gl.uniform2f(l, v[0], v[1]);
        else if (v.length === 3) gl.uniform3f(l, v[0], v[1], v[2]);
        else gl.uniform4f(l, v[0], v[1], v[2], v[3]);
      }
    },
    tex(n, unit, texture) {
      gl.activeTexture(gl.TEXTURE0 + unit);
      gl.bindTexture(gl.TEXTURE_2D, texture);
      const l = loc(n);
      if (l !== null) gl.uniform1i(l, unit);
    },
  };
}

/** A grid over 0..1 by 0..1. Its triangles face the viewer. */
export function grid(gl, nx, ny) {
  const at = new Float32Array((nx + 1) * (ny + 1) * 2);
  for (let j = 0, k = 0; j <= ny; j++) for (let i = 0; i <= nx; i++) { at[k++] = i / nx; at[k++] = j / ny; }
  const ix = new Uint16Array(nx * ny * 6);
  for (let j = 0, k = 0; j < ny; j++) {
    for (let i = 0; i < nx; i++) {
      const p = j * (nx + 1) + i, q = p + nx + 1;
      ix.set([p, q, p + 1, p + 1, q, q + 1], k);
      k += 6;
    }
  }
  const vao = gl.createVertexArray();
  gl.bindVertexArray(vao);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, at, gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, ix, gl.STATIC_DRAW);
  gl.bindVertexArray(null);
  return { draw() { gl.bindVertexArray(vao); gl.drawElements(gl.TRIANGLES, ix.length, gl.UNSIGNED_SHORT, 0); } };
}

export function image(url) {
  return new Promise((ok, bad) => {
    const img = new Image();
    img.onload = () => img.decode().then(() => ok(img), () => ok(img));
    img.onerror = () => bad(new Error(url));
    img.src = url;
  });
}

export function texture(gl, source, { mips = true, repeat = false } = {}) {
  const t = gl.createTexture();
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, t);
  const wrap = repeat ? gl.REPEAT : gl.CLAMP_TO_EDGE;
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, wrap);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, wrap);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, mips ? gl.LINEAR_MIPMAP_LINEAR : gl.LINEAR);
  if (source) {
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, source);
    if (mips) gl.generateMipmap(gl.TEXTURE_2D);
    const aniso = gl.getExtension("EXT_texture_filter_anisotropic");
    if (aniso && mips) gl.texParameterf(gl.TEXTURE_2D, aniso.TEXTURE_MAX_ANISOTROPY_EXT, 4);
  }
  return t;
}

/** World to clip for a stage [w] by [h] design units wide at z = 0, seen from DIST in front of it. */
export function camera(w, h, shakeX = 0, shakeY = 0) {
  const near = 200, far = 3400;
  const a = (far + near) / (near - far), b = (2 * far * near) / (near - far);
  const sx = (2 / w) * DIST, sy = (-2 / h) * DIST;
  // z' = z - DIST; w = -z'
  return new Float32Array([sx, 0, 0, 0, 0, sy, 0, 0, 0, 0, a, -1, sx * shakeX, sy * shakeY, -DIST * a + b, DIST]);
}

export const ident = () => new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
export function mul(a, b) {
  const o = new Float32Array(16);
  for (let c = 0; c < 4; c++) {
    for (let r = 0; r < 4; r++) o[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3];
  }
  return o;
}
export const move = (x, y, z) => new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1]);
export const scale = (x, y = x, z = x) => new Float32Array([x, 0, 0, 0, 0, y, 0, 0, 0, 0, z, 0, 0, 0, 0, 1]);
export function rotX(r) { const c = Math.cos(r), s = Math.sin(r); return new Float32Array([1, 0, 0, 0, 0, c, s, 0, 0, -s, c, 0, 0, 0, 0, 1]); }
export function rotY(r) { const c = Math.cos(r), s = Math.sin(r); return new Float32Array([c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 0, 0, 0, 1]); }
export function rotZ(r) { const c = Math.cos(r), s = Math.sin(r); return new Float32Array([c, s, 0, 0, -s, c, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]); }
const RAD = Math.PI / 180;
/** Move, then lean: angles in degrees, as CSS has them. */
export function pose(p) {
  let m = move(p.x, p.y, p.z);
  if (p.rz) m = mul(m, rotZ(p.rz * RAD));
  if (p.ry) m = mul(m, rotY(p.ry * RAD));
  if (p.rx) m = mul(m, rotX(p.rx * RAD));
  if (p.s !== 1 || p.sy) m = mul(m, scale(p.s * (p.sx ?? 1), p.s * (p.sy ?? 1), p.s));
  return m;
}
