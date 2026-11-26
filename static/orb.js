// The voice orb - a glowing WebGL ball in the middle of the HUD.
// Ported from the "voice-powered-orb" React component to plain WebGL (no React, no ogl).
// Instead of listening to a microphone, it listens to JARVIS himself:
//   idle     -> turns slowly, calm
//   thinking -> a little restless
//   speaking -> wobbles and spins with a fake "voice level"
//
// Use:  const orb = JarvisOrb(document.getElementById("orb"));  orb.setMode("speaking");

window.JarvisOrb = function JarvisOrb(container, options = {}) {
  const hue = options.hue ?? 0;
  const maxRotationSpeed = options.maxRotationSpeed ?? 1.2;
  const maxHoverIntensity = options.maxHoverIntensity ?? 0.8;

  const VERT = `
    precision highp float;
    attribute vec2 position;
    attribute vec2 uv;
    varying vec2 vUv;
    void main() { vUv = uv; gl_Position = vec4(position, 0.0, 1.0); }
  `;

  // Same shader as the original component.
  const FRAG = `
    precision highp float;
    uniform float iTime;
    uniform vec3 iResolution;
    uniform float hue;
    uniform float hover;
    uniform float rot;
    uniform float hoverIntensity;
    varying vec2 vUv;

    vec3 rgb2yiq(vec3 c) {
      float y = dot(c, vec3(0.299, 0.587, 0.114));
      float i = dot(c, vec3(0.596, -0.274, -0.322));
      float q = dot(c, vec3(0.211, -0.523, 0.312));
      return vec3(y, i, q);
    }
    vec3 yiq2rgb(vec3 c) {
      return vec3(c.x + 0.956 * c.y + 0.621 * c.z,
                  c.x - 0.272 * c.y - 0.647 * c.z,
                  c.x - 1.106 * c.y + 1.703 * c.z);
    }
    vec3 adjustHue(vec3 color, float hueDeg) {
      float hueRad = hueDeg * 3.14159265 / 180.0;
      vec3 yiq = rgb2yiq(color);
      float cosA = cos(hueRad), sinA = sin(hueRad);
      float i = yiq.y * cosA - yiq.z * sinA;
      float q = yiq.y * sinA + yiq.z * cosA;
      yiq.y = i; yiq.z = q;
      return yiq2rgb(yiq);
    }
    vec3 hash33(vec3 p3) {
      p3 = fract(p3 * vec3(0.1031, 0.11369, 0.13787));
      p3 += dot(p3, p3.yxz + 19.19);
      return -1.0 + 2.0 * fract(vec3(p3.x + p3.y, p3.x + p3.z, p3.y + p3.z) * p3.zyx);
    }
    float snoise3(vec3 p) {
      const float K1 = 0.333333333;
      const float K2 = 0.166666667;
      vec3 i = floor(p + (p.x + p.y + p.z) * K1);
      vec3 d0 = p - (i - (i.x + i.y + i.z) * K2);
      vec3 e = step(vec3(0.0), d0 - d0.yzx);
      vec3 i1 = e * (1.0 - e.zxy);
      vec3 i2 = 1.0 - e.zxy * (1.0 - e);
      vec3 d1 = d0 - (i1 - K2);
      vec3 d2 = d0 - (i2 - K1);
      vec3 d3 = d0 - 0.5;
      vec4 h = max(0.6 - vec4(dot(d0, d0), dot(d1, d1), dot(d2, d2), dot(d3, d3)), 0.0);
      vec4 n = h * h * h * h * vec4(dot(d0, hash33(i)), dot(d1, hash33(i + i1)),
                                    dot(d2, hash33(i + i2)), dot(d3, hash33(i + 1.0)));
      return dot(vec4(31.316), n);
    }
    vec4 extractAlpha(vec3 colorIn) {
      float a = max(max(colorIn.r, colorIn.g), colorIn.b);
      return vec4(colorIn.rgb / (a + 1e-5), a);
    }

    const vec3 baseColor1 = vec3(0.611765, 0.262745, 0.996078);
    const vec3 baseColor2 = vec3(0.298039, 0.760784, 0.913725);
    const vec3 baseColor3 = vec3(0.062745, 0.078431, 0.600000);
    const float innerRadius = 0.6;
    const float noiseScale = 0.65;

    float light1(float intensity, float attenuation, float dist) { return intensity / (1.0 + dist * attenuation); }
    float light2(float intensity, float attenuation, float dist) { return intensity / (1.0 + dist * dist * attenuation); }

    vec4 draw(vec2 uv) {
      vec3 color1 = adjustHue(baseColor1, hue);
      vec3 color2 = adjustHue(baseColor2, hue);
      vec3 color3 = adjustHue(baseColor3, hue);
      float ang = atan(uv.y, uv.x);
      float len = length(uv);
      float invLen = len > 0.0 ? 1.0 / len : 0.0;

      float n0 = snoise3(vec3(uv * noiseScale, iTime * 0.5)) * 0.5 + 0.5;
      float r0 = mix(mix(innerRadius, 1.0, 0.4), mix(innerRadius, 1.0, 0.6), n0);
      float d0 = distance(uv, (r0 * invLen) * uv);
      float v0 = light1(1.0, 10.0, d0);
      v0 *= smoothstep(r0 * 1.05, r0, len);
      float cl = cos(ang + iTime * 2.0) * 0.5 + 0.5;

      float a = iTime * -1.0;
      vec2 pos = vec2(cos(a), sin(a)) * r0;
      float d = distance(uv, pos);
      float v1 = light2(1.5, 5.0, d);
      v1 *= light1(1.0, 50.0, d0);

      float v2 = smoothstep(1.0, mix(innerRadius, 1.0, n0 * 0.5), len);
      float v3 = smoothstep(innerRadius, mix(innerRadius, 1.0, 0.5), len);

      vec3 col = mix(color1, color2, cl);
      col = mix(color3, col, v0);
      col = (col + v1) * v2 * v3;
      col = clamp(col, 0.0, 1.0);
      return extractAlpha(col);
    }

    vec4 mainImage(vec2 fragCoord) {
      vec2 center = iResolution.xy * 0.5;
      float size = min(iResolution.x, iResolution.y);
      vec2 uv = (fragCoord - center) / size * 2.0;
      float s = sin(rot), c = cos(rot);
      uv = vec2(c * uv.x - s * uv.y, s * uv.x + c * uv.y);
      uv.x += hover * hoverIntensity * 0.1 * sin(uv.y * 10.0 + iTime);
      uv.y += hover * hoverIntensity * 0.1 * sin(uv.x * 10.0 + iTime);
      return draw(uv);
    }

    void main() {
      vec4 col = mainImage(vUv * iResolution.xy);
      gl_FragColor = vec4(col.rgb * col.a, col.a);
    }
  `;

  const canvas = document.createElement("canvas");
  container.append(canvas);
  const gl = canvas.getContext("webgl", { alpha: true, premultipliedAlpha: false, antialias: true });
  if (!gl) {  // very old browser: show a plain glowing circle instead
    container.classList.add("orb-fallback");
    return { setMode() {} };
  }

  function compile(type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
    return shader;
  }
  const program = gl.createProgram();
  gl.attachShader(program, compile(gl.VERTEX_SHADER, VERT));
  gl.attachShader(program, compile(gl.FRAGMENT_SHADER, FRAG));
  gl.linkProgram(program);
  gl.useProgram(program);

  // One big triangle that covers the whole canvas.
  function attribute(name, data) {
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(data), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(program, name);
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  }
  attribute("position", [-1, -1, 3, -1, -1, 3]);
  attribute("uv", [0, 0, 2, 0, 0, 2]);

  const u = {};
  for (const name of ["iTime", "iResolution", "hue", "hover", "rot", "hoverIntensity"]) {
    u[name] = gl.getUniformLocation(program, name);
  }
  gl.uniform1f(u.hue, hue);
  gl.clearColor(0, 0, 0, 0);
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = container.clientWidth, h = container.clientHeight;
    if (!w || !h) return;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.uniform3f(u.iResolution, canvas.width, canvas.height, canvas.width / canvas.height);
  }
  new ResizeObserver(resize).observe(container);
  resize();

  // ---- the "voice": a made-up loudness that rises and falls like speech ----
  let mode = "idle";
  let level = 0;   // smoothed 0..1
  let rot = 0;
  let last = performance.now();

  function targetLevel(t) {
    if (mode === "speaking") {
      // a few sine waves at syllable speed (~3-7 per second) = a believable talking rhythm
      const syllables = Math.abs(Math.sin(t * 5.3) * 0.6 + Math.sin(t * 8.9 + 1.3) * 0.3 + Math.sin(t * 2.1) * 0.25);
      return 0.25 + 0.6 * Math.min(1, syllables);
    }
    if (mode === "thinking") return 0.12 + 0.06 * Math.sin(t * 3);
    return 0;
  }

  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  function frame(now) {
    requestAnimationFrame(frame);
    if (document.hidden) return;
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    const t = now / 1000;

    const target = targetLevel(t);
    level += (target - level) * (target > level ? 0.25 : 0.06);  // quick to rise, slow to settle

    // idle still turns, just slowly ("steady")
    rot += dt * (0.12 + level * maxRotationSpeed * 2.0);

    gl.uniform1f(u.iTime, reduced ? 0 : t);
    gl.uniform1f(u.rot, rot);
    gl.uniform1f(u.hover, Math.min(level * 2.0, 1.0));
    gl.uniform1f(u.hoverIntensity, Math.min(level * maxHoverIntensity * 0.8, maxHoverIntensity));
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    container.style.setProperty("--level", level.toFixed(3));
  }
  requestAnimationFrame(frame);

  return {
    setMode(next) { mode = next; },
    get level() { return level; },
  };
};
