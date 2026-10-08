/* @bruk-io/bh-01 0.0.1 (MIT), built from https://github.com/bruk-io/bh-01 at 73304968d1bdb9e04fad3b7881611cef2792832e with lit 3.3.2 and @lit/context 1.1.6 (BSD-3-Clause) bundled in by esbuild 0.27.3. See VENDOR.md beside this file. */

// node_modules/@lit/reactive-element/css-tag.js
var t = globalThis;
var e = t.ShadowRoot && (void 0 === t.ShadyCSS || t.ShadyCSS.nativeShadow) && "adoptedStyleSheets" in Document.prototype && "replace" in CSSStyleSheet.prototype;
var s = /* @__PURE__ */ Symbol();
var o = /* @__PURE__ */ new WeakMap();
var n = class {
  constructor(t20, e31, o20) {
    if (this._$cssResult$ = true, o20 !== s) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
    this.cssText = t20, this.t = e31;
  }
  get styleSheet() {
    let t20 = this.o;
    const s16 = this.t;
    if (e && void 0 === t20) {
      const e31 = void 0 !== s16 && 1 === s16.length;
      e31 && (t20 = o.get(s16)), void 0 === t20 && ((this.o = t20 = new CSSStyleSheet()).replaceSync(this.cssText), e31 && o.set(s16, t20));
    }
    return t20;
  }
  toString() {
    return this.cssText;
  }
};
var r = (t20) => new n("string" == typeof t20 ? t20 : t20 + "", void 0, s);
var i = (t20, ...e31) => {
  const o20 = 1 === t20.length ? t20[0] : e31.reduce((e32, s16, o21) => e32 + ((t21) => {
    if (true === t21._$cssResult$) return t21.cssText;
    if ("number" == typeof t21) return t21;
    throw Error("Value passed to 'css' function must be a 'css' function result: " + t21 + ". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.");
  })(s16) + t20[o21 + 1], t20[0]);
  return new n(o20, t20, s);
};
var S = (s16, o20) => {
  if (e) s16.adoptedStyleSheets = o20.map((t20) => t20 instanceof CSSStyleSheet ? t20 : t20.styleSheet);
  else for (const e31 of o20) {
    const o21 = document.createElement("style"), n14 = t.litNonce;
    void 0 !== n14 && o21.setAttribute("nonce", n14), o21.textContent = e31.cssText, s16.appendChild(o21);
  }
};
var c = e ? (t20) => t20 : (t20) => t20 instanceof CSSStyleSheet ? ((t21) => {
  let e31 = "";
  for (const s16 of t21.cssRules) e31 += s16.cssText;
  return r(e31);
})(t20) : t20;

// node_modules/@lit/reactive-element/reactive-element.js
var { is: i2, defineProperty: e2, getOwnPropertyDescriptor: h, getOwnPropertyNames: r2, getOwnPropertySymbols: o2, getPrototypeOf: n2 } = Object;
var a = globalThis;
var c2 = a.trustedTypes;
var l = c2 ? c2.emptyScript : "";
var p = a.reactiveElementPolyfillSupport;
var d = (t20, s16) => t20;
var u = { toAttribute(t20, s16) {
  switch (s16) {
    case Boolean:
      t20 = t20 ? l : null;
      break;
    case Object:
    case Array:
      t20 = null == t20 ? t20 : JSON.stringify(t20);
  }
  return t20;
}, fromAttribute(t20, s16) {
  let i20 = t20;
  switch (s16) {
    case Boolean:
      i20 = null !== t20;
      break;
    case Number:
      i20 = null === t20 ? null : Number(t20);
      break;
    case Object:
    case Array:
      try {
        i20 = JSON.parse(t20);
      } catch (t21) {
        i20 = null;
      }
  }
  return i20;
} };
var f = (t20, s16) => !i2(t20, s16);
var b = { attribute: true, type: String, converter: u, reflect: false, useDefault: false, hasChanged: f };
Symbol.metadata ??= /* @__PURE__ */ Symbol("metadata"), a.litPropertyMetadata ??= /* @__PURE__ */ new WeakMap();
var y = class extends HTMLElement {
  static addInitializer(t20) {
    this._$Ei(), (this.l ??= []).push(t20);
  }
  static get observedAttributes() {
    return this.finalize(), this._$Eh && [...this._$Eh.keys()];
  }
  static createProperty(t20, s16 = b) {
    if (s16.state && (s16.attribute = false), this._$Ei(), this.prototype.hasOwnProperty(t20) && ((s16 = Object.create(s16)).wrapped = true), this.elementProperties.set(t20, s16), !s16.noAccessor) {
      const i20 = /* @__PURE__ */ Symbol(), h11 = this.getPropertyDescriptor(t20, i20, s16);
      void 0 !== h11 && e2(this.prototype, t20, h11);
    }
  }
  static getPropertyDescriptor(t20, s16, i20) {
    const { get: e31, set: r28 } = h(this.prototype, t20) ?? { get() {
      return this[s16];
    }, set(t21) {
      this[s16] = t21;
    } };
    return { get: e31, set(s17) {
      const h11 = e31?.call(this);
      r28?.call(this, s17), this.requestUpdate(t20, h11, i20);
    }, configurable: true, enumerable: true };
  }
  static getPropertyOptions(t20) {
    return this.elementProperties.get(t20) ?? b;
  }
  static _$Ei() {
    if (this.hasOwnProperty(d("elementProperties"))) return;
    const t20 = n2(this);
    t20.finalize(), void 0 !== t20.l && (this.l = [...t20.l]), this.elementProperties = new Map(t20.elementProperties);
  }
  static finalize() {
    if (this.hasOwnProperty(d("finalized"))) return;
    if (this.finalized = true, this._$Ei(), this.hasOwnProperty(d("properties"))) {
      const t21 = this.properties, s16 = [...r2(t21), ...o2(t21)];
      for (const i20 of s16) this.createProperty(i20, t21[i20]);
    }
    const t20 = this[Symbol.metadata];
    if (null !== t20) {
      const s16 = litPropertyMetadata.get(t20);
      if (void 0 !== s16) for (const [t21, i20] of s16) this.elementProperties.set(t21, i20);
    }
    this._$Eh = /* @__PURE__ */ new Map();
    for (const [t21, s16] of this.elementProperties) {
      const i20 = this._$Eu(t21, s16);
      void 0 !== i20 && this._$Eh.set(i20, t21);
    }
    this.elementStyles = this.finalizeStyles(this.styles);
  }
  static finalizeStyles(s16) {
    const i20 = [];
    if (Array.isArray(s16)) {
      const e31 = new Set(s16.flat(1 / 0).reverse());
      for (const s17 of e31) i20.unshift(c(s17));
    } else void 0 !== s16 && i20.push(c(s16));
    return i20;
  }
  static _$Eu(t20, s16) {
    const i20 = s16.attribute;
    return false === i20 ? void 0 : "string" == typeof i20 ? i20 : "string" == typeof t20 ? t20.toLowerCase() : void 0;
  }
  constructor() {
    super(), this._$Ep = void 0, this.isUpdatePending = false, this.hasUpdated = false, this._$Em = null, this._$Ev();
  }
  _$Ev() {
    this._$ES = new Promise((t20) => this.enableUpdating = t20), this._$AL = /* @__PURE__ */ new Map(), this._$E_(), this.requestUpdate(), this.constructor.l?.forEach((t20) => t20(this));
  }
  addController(t20) {
    (this._$EO ??= /* @__PURE__ */ new Set()).add(t20), void 0 !== this.renderRoot && this.isConnected && t20.hostConnected?.();
  }
  removeController(t20) {
    this._$EO?.delete(t20);
  }
  _$E_() {
    const t20 = /* @__PURE__ */ new Map(), s16 = this.constructor.elementProperties;
    for (const i20 of s16.keys()) this.hasOwnProperty(i20) && (t20.set(i20, this[i20]), delete this[i20]);
    t20.size > 0 && (this._$Ep = t20);
  }
  createRenderRoot() {
    const t20 = this.shadowRoot ?? this.attachShadow(this.constructor.shadowRootOptions);
    return S(t20, this.constructor.elementStyles), t20;
  }
  connectedCallback() {
    this.renderRoot ??= this.createRenderRoot(), this.enableUpdating(true), this._$EO?.forEach((t20) => t20.hostConnected?.());
  }
  enableUpdating(t20) {
  }
  disconnectedCallback() {
    this._$EO?.forEach((t20) => t20.hostDisconnected?.());
  }
  attributeChangedCallback(t20, s16, i20) {
    this._$AK(t20, i20);
  }
  _$ET(t20, s16) {
    const i20 = this.constructor.elementProperties.get(t20), e31 = this.constructor._$Eu(t20, i20);
    if (void 0 !== e31 && true === i20.reflect) {
      const h11 = (void 0 !== i20.converter?.toAttribute ? i20.converter : u).toAttribute(s16, i20.type);
      this._$Em = t20, null == h11 ? this.removeAttribute(e31) : this.setAttribute(e31, h11), this._$Em = null;
    }
  }
  _$AK(t20, s16) {
    const i20 = this.constructor, e31 = i20._$Eh.get(t20);
    if (void 0 !== e31 && this._$Em !== e31) {
      const t21 = i20.getPropertyOptions(e31), h11 = "function" == typeof t21.converter ? { fromAttribute: t21.converter } : void 0 !== t21.converter?.fromAttribute ? t21.converter : u;
      this._$Em = e31;
      const r28 = h11.fromAttribute(s16, t21.type);
      this[e31] = r28 ?? this._$Ej?.get(e31) ?? r28, this._$Em = null;
    }
  }
  requestUpdate(t20, s16, i20, e31 = false, h11) {
    if (void 0 !== t20) {
      const r28 = this.constructor;
      if (false === e31 && (h11 = this[t20]), i20 ??= r28.getPropertyOptions(t20), !((i20.hasChanged ?? f)(h11, s16) || i20.useDefault && i20.reflect && h11 === this._$Ej?.get(t20) && !this.hasAttribute(r28._$Eu(t20, i20)))) return;
      this.C(t20, s16, i20);
    }
    false === this.isUpdatePending && (this._$ES = this._$EP());
  }
  C(t20, s16, { useDefault: i20, reflect: e31, wrapped: h11 }, r28) {
    i20 && !(this._$Ej ??= /* @__PURE__ */ new Map()).has(t20) && (this._$Ej.set(t20, r28 ?? s16 ?? this[t20]), true !== h11 || void 0 !== r28) || (this._$AL.has(t20) || (this.hasUpdated || i20 || (s16 = void 0), this._$AL.set(t20, s16)), true === e31 && this._$Em !== t20 && (this._$Eq ??= /* @__PURE__ */ new Set()).add(t20));
  }
  async _$EP() {
    this.isUpdatePending = true;
    try {
      await this._$ES;
    } catch (t21) {
      Promise.reject(t21);
    }
    const t20 = this.scheduleUpdate();
    return null != t20 && await t20, !this.isUpdatePending;
  }
  scheduleUpdate() {
    return this.performUpdate();
  }
  performUpdate() {
    if (!this.isUpdatePending) return;
    if (!this.hasUpdated) {
      if (this.renderRoot ??= this.createRenderRoot(), this._$Ep) {
        for (const [t22, s17] of this._$Ep) this[t22] = s17;
        this._$Ep = void 0;
      }
      const t21 = this.constructor.elementProperties;
      if (t21.size > 0) for (const [s17, i20] of t21) {
        const { wrapped: t22 } = i20, e31 = this[s17];
        true !== t22 || this._$AL.has(s17) || void 0 === e31 || this.C(s17, void 0, i20, e31);
      }
    }
    let t20 = false;
    const s16 = this._$AL;
    try {
      t20 = this.shouldUpdate(s16), t20 ? (this.willUpdate(s16), this._$EO?.forEach((t21) => t21.hostUpdate?.()), this.update(s16)) : this._$EM();
    } catch (s17) {
      throw t20 = false, this._$EM(), s17;
    }
    t20 && this._$AE(s16);
  }
  willUpdate(t20) {
  }
  _$AE(t20) {
    this._$EO?.forEach((t21) => t21.hostUpdated?.()), this.hasUpdated || (this.hasUpdated = true, this.firstUpdated(t20)), this.updated(t20);
  }
  _$EM() {
    this._$AL = /* @__PURE__ */ new Map(), this.isUpdatePending = false;
  }
  get updateComplete() {
    return this.getUpdateComplete();
  }
  getUpdateComplete() {
    return this._$ES;
  }
  shouldUpdate(t20) {
    return true;
  }
  update(t20) {
    this._$Eq &&= this._$Eq.forEach((t21) => this._$ET(t21, this[t21])), this._$EM();
  }
  updated(t20) {
  }
  firstUpdated(t20) {
  }
};
y.elementStyles = [], y.shadowRootOptions = { mode: "open" }, y[d("elementProperties")] = /* @__PURE__ */ new Map(), y[d("finalized")] = /* @__PURE__ */ new Map(), p?.({ ReactiveElement: y }), (a.reactiveElementVersions ??= []).push("2.1.2");

// node_modules/lit-html/lit-html.js
var t2 = globalThis;
var i3 = (t20) => t20;
var s2 = t2.trustedTypes;
var e3 = s2 ? s2.createPolicy("lit-html", { createHTML: (t20) => t20 }) : void 0;
var h2 = "$lit$";
var o3 = `lit$${Math.random().toFixed(9).slice(2)}$`;
var n3 = "?" + o3;
var r3 = `<${n3}>`;
var l2 = document;
var c3 = () => l2.createComment("");
var a2 = (t20) => null === t20 || "object" != typeof t20 && "function" != typeof t20;
var u2 = Array.isArray;
var d2 = (t20) => u2(t20) || "function" == typeof t20?.[Symbol.iterator];
var f2 = "[ 	\n\f\r]";
var v = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g;
var _ = /-->/g;
var m = />/g;
var p2 = RegExp(`>|${f2}(?:([^\\s"'>=/]+)(${f2}*=${f2}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`, "g");
var g = /'/g;
var $ = /"/g;
var y2 = /^(?:script|style|textarea|title)$/i;
var x = (t20) => (i20, ...s16) => ({ _$litType$: t20, strings: i20, values: s16 });
var b2 = x(1);
var w = x(2);
var T = x(3);
var E = /* @__PURE__ */ Symbol.for("lit-noChange");
var A = /* @__PURE__ */ Symbol.for("lit-nothing");
var C = /* @__PURE__ */ new WeakMap();
var P = l2.createTreeWalker(l2, 129);
function V(t20, i20) {
  if (!u2(t20) || !t20.hasOwnProperty("raw")) throw Error("invalid template strings array");
  return void 0 !== e3 ? e3.createHTML(i20) : i20;
}
var N = (t20, i20) => {
  const s16 = t20.length - 1, e31 = [];
  let n14, l10 = 2 === i20 ? "<svg>" : 3 === i20 ? "<math>" : "", c16 = v;
  for (let i21 = 0; i21 < s16; i21++) {
    const s17 = t20[i21];
    let a20, u13, d19 = -1, f24 = 0;
    for (; f24 < s17.length && (c16.lastIndex = f24, u13 = c16.exec(s17), null !== u13); ) f24 = c16.lastIndex, c16 === v ? "!--" === u13[1] ? c16 = _ : void 0 !== u13[1] ? c16 = m : void 0 !== u13[2] ? (y2.test(u13[2]) && (n14 = RegExp("</" + u13[2], "g")), c16 = p2) : void 0 !== u13[3] && (c16 = p2) : c16 === p2 ? ">" === u13[0] ? (c16 = n14 ?? v, d19 = -1) : void 0 === u13[1] ? d19 = -2 : (d19 = c16.lastIndex - u13[2].length, a20 = u13[1], c16 = void 0 === u13[3] ? p2 : '"' === u13[3] ? $ : g) : c16 === $ || c16 === g ? c16 = p2 : c16 === _ || c16 === m ? c16 = v : (c16 = p2, n14 = void 0);
    const x4 = c16 === p2 && t20[i21 + 1].startsWith("/>") ? " " : "";
    l10 += c16 === v ? s17 + r3 : d19 >= 0 ? (e31.push(a20), s17.slice(0, d19) + h2 + s17.slice(d19) + o3 + x4) : s17 + o3 + (-2 === d19 ? i21 : x4);
  }
  return [V(t20, l10 + (t20[s16] || "<?>") + (2 === i20 ? "</svg>" : 3 === i20 ? "</math>" : "")), e31];
};
var S2 = class _S {
  constructor({ strings: t20, _$litType$: i20 }, e31) {
    let r28;
    this.parts = [];
    let l10 = 0, a20 = 0;
    const u13 = t20.length - 1, d19 = this.parts, [f24, v22] = N(t20, i20);
    if (this.el = _S.createElement(f24, e31), P.currentNode = this.el.content, 2 === i20 || 3 === i20) {
      const t21 = this.el.content.firstChild;
      t21.replaceWith(...t21.childNodes);
    }
    for (; null !== (r28 = P.nextNode()) && d19.length < u13; ) {
      if (1 === r28.nodeType) {
        if (r28.hasAttributes()) for (const t21 of r28.getAttributeNames()) if (t21.endsWith(h2)) {
          const i21 = v22[a20++], s16 = r28.getAttribute(t21).split(o3), e32 = /([.?@])?(.*)/.exec(i21);
          d19.push({ type: 1, index: l10, name: e32[2], strings: s16, ctor: "." === e32[1] ? I : "?" === e32[1] ? L : "@" === e32[1] ? z : H }), r28.removeAttribute(t21);
        } else t21.startsWith(o3) && (d19.push({ type: 6, index: l10 }), r28.removeAttribute(t21));
        if (y2.test(r28.tagName)) {
          const t21 = r28.textContent.split(o3), i21 = t21.length - 1;
          if (i21 > 0) {
            r28.textContent = s2 ? s2.emptyScript : "";
            for (let s16 = 0; s16 < i21; s16++) r28.append(t21[s16], c3()), P.nextNode(), d19.push({ type: 2, index: ++l10 });
            r28.append(t21[i21], c3());
          }
        }
      } else if (8 === r28.nodeType) if (r28.data === n3) d19.push({ type: 2, index: l10 });
      else {
        let t21 = -1;
        for (; -1 !== (t21 = r28.data.indexOf(o3, t21 + 1)); ) d19.push({ type: 7, index: l10 }), t21 += o3.length - 1;
      }
      l10++;
    }
  }
  static createElement(t20, i20) {
    const s16 = l2.createElement("template");
    return s16.innerHTML = t20, s16;
  }
};
function M(t20, i20, s16 = t20, e31) {
  if (i20 === E) return i20;
  let h11 = void 0 !== e31 ? s16._$Co?.[e31] : s16._$Cl;
  const o20 = a2(i20) ? void 0 : i20._$litDirective$;
  return h11?.constructor !== o20 && (h11?._$AO?.(false), void 0 === o20 ? h11 = void 0 : (h11 = new o20(t20), h11._$AT(t20, s16, e31)), void 0 !== e31 ? (s16._$Co ??= [])[e31] = h11 : s16._$Cl = h11), void 0 !== h11 && (i20 = M(t20, h11._$AS(t20, i20.values), h11, e31)), i20;
}
var R = class {
  constructor(t20, i20) {
    this._$AV = [], this._$AN = void 0, this._$AD = t20, this._$AM = i20;
  }
  get parentNode() {
    return this._$AM.parentNode;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  u(t20) {
    const { el: { content: i20 }, parts: s16 } = this._$AD, e31 = (t20?.creationScope ?? l2).importNode(i20, true);
    P.currentNode = e31;
    let h11 = P.nextNode(), o20 = 0, n14 = 0, r28 = s16[0];
    for (; void 0 !== r28; ) {
      if (o20 === r28.index) {
        let i21;
        2 === r28.type ? i21 = new k(h11, h11.nextSibling, this, t20) : 1 === r28.type ? i21 = new r28.ctor(h11, r28.name, r28.strings, this, t20) : 6 === r28.type && (i21 = new Z(h11, this, t20)), this._$AV.push(i21), r28 = s16[++n14];
      }
      o20 !== r28?.index && (h11 = P.nextNode(), o20++);
    }
    return P.currentNode = l2, e31;
  }
  p(t20) {
    let i20 = 0;
    for (const s16 of this._$AV) void 0 !== s16 && (void 0 !== s16.strings ? (s16._$AI(t20, s16, i20), i20 += s16.strings.length - 2) : s16._$AI(t20[i20])), i20++;
  }
};
var k = class _k {
  get _$AU() {
    return this._$AM?._$AU ?? this._$Cv;
  }
  constructor(t20, i20, s16, e31) {
    this.type = 2, this._$AH = A, this._$AN = void 0, this._$AA = t20, this._$AB = i20, this._$AM = s16, this.options = e31, this._$Cv = e31?.isConnected ?? true;
  }
  get parentNode() {
    let t20 = this._$AA.parentNode;
    const i20 = this._$AM;
    return void 0 !== i20 && 11 === t20?.nodeType && (t20 = i20.parentNode), t20;
  }
  get startNode() {
    return this._$AA;
  }
  get endNode() {
    return this._$AB;
  }
  _$AI(t20, i20 = this) {
    t20 = M(this, t20, i20), a2(t20) ? t20 === A || null == t20 || "" === t20 ? (this._$AH !== A && this._$AR(), this._$AH = A) : t20 !== this._$AH && t20 !== E && this._(t20) : void 0 !== t20._$litType$ ? this.$(t20) : void 0 !== t20.nodeType ? this.T(t20) : d2(t20) ? this.k(t20) : this._(t20);
  }
  O(t20) {
    return this._$AA.parentNode.insertBefore(t20, this._$AB);
  }
  T(t20) {
    this._$AH !== t20 && (this._$AR(), this._$AH = this.O(t20));
  }
  _(t20) {
    this._$AH !== A && a2(this._$AH) ? this._$AA.nextSibling.data = t20 : this.T(l2.createTextNode(t20)), this._$AH = t20;
  }
  $(t20) {
    const { values: i20, _$litType$: s16 } = t20, e31 = "number" == typeof s16 ? this._$AC(t20) : (void 0 === s16.el && (s16.el = S2.createElement(V(s16.h, s16.h[0]), this.options)), s16);
    if (this._$AH?._$AD === e31) this._$AH.p(i20);
    else {
      const t21 = new R(e31, this), s17 = t21.u(this.options);
      t21.p(i20), this.T(s17), this._$AH = t21;
    }
  }
  _$AC(t20) {
    let i20 = C.get(t20.strings);
    return void 0 === i20 && C.set(t20.strings, i20 = new S2(t20)), i20;
  }
  k(t20) {
    u2(this._$AH) || (this._$AH = [], this._$AR());
    const i20 = this._$AH;
    let s16, e31 = 0;
    for (const h11 of t20) e31 === i20.length ? i20.push(s16 = new _k(this.O(c3()), this.O(c3()), this, this.options)) : s16 = i20[e31], s16._$AI(h11), e31++;
    e31 < i20.length && (this._$AR(s16 && s16._$AB.nextSibling, e31), i20.length = e31);
  }
  _$AR(t20 = this._$AA.nextSibling, s16) {
    for (this._$AP?.(false, true, s16); t20 !== this._$AB; ) {
      const s17 = i3(t20).nextSibling;
      i3(t20).remove(), t20 = s17;
    }
  }
  setConnected(t20) {
    void 0 === this._$AM && (this._$Cv = t20, this._$AP?.(t20));
  }
};
var H = class {
  get tagName() {
    return this.element.tagName;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  constructor(t20, i20, s16, e31, h11) {
    this.type = 1, this._$AH = A, this._$AN = void 0, this.element = t20, this.name = i20, this._$AM = e31, this.options = h11, s16.length > 2 || "" !== s16[0] || "" !== s16[1] ? (this._$AH = Array(s16.length - 1).fill(new String()), this.strings = s16) : this._$AH = A;
  }
  _$AI(t20, i20 = this, s16, e31) {
    const h11 = this.strings;
    let o20 = false;
    if (void 0 === h11) t20 = M(this, t20, i20, 0), o20 = !a2(t20) || t20 !== this._$AH && t20 !== E, o20 && (this._$AH = t20);
    else {
      const e32 = t20;
      let n14, r28;
      for (t20 = h11[0], n14 = 0; n14 < h11.length - 1; n14++) r28 = M(this, e32[s16 + n14], i20, n14), r28 === E && (r28 = this._$AH[n14]), o20 ||= !a2(r28) || r28 !== this._$AH[n14], r28 === A ? t20 = A : t20 !== A && (t20 += (r28 ?? "") + h11[n14 + 1]), this._$AH[n14] = r28;
    }
    o20 && !e31 && this.j(t20);
  }
  j(t20) {
    t20 === A ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, t20 ?? "");
  }
};
var I = class extends H {
  constructor() {
    super(...arguments), this.type = 3;
  }
  j(t20) {
    this.element[this.name] = t20 === A ? void 0 : t20;
  }
};
var L = class extends H {
  constructor() {
    super(...arguments), this.type = 4;
  }
  j(t20) {
    this.element.toggleAttribute(this.name, !!t20 && t20 !== A);
  }
};
var z = class extends H {
  constructor(t20, i20, s16, e31, h11) {
    super(t20, i20, s16, e31, h11), this.type = 5;
  }
  _$AI(t20, i20 = this) {
    if ((t20 = M(this, t20, i20, 0) ?? A) === E) return;
    const s16 = this._$AH, e31 = t20 === A && s16 !== A || t20.capture !== s16.capture || t20.once !== s16.once || t20.passive !== s16.passive, h11 = t20 !== A && (s16 === A || e31);
    e31 && this.element.removeEventListener(this.name, this, s16), h11 && this.element.addEventListener(this.name, this, t20), this._$AH = t20;
  }
  handleEvent(t20) {
    "function" == typeof this._$AH ? this._$AH.call(this.options?.host ?? this.element, t20) : this._$AH.handleEvent(t20);
  }
};
var Z = class {
  constructor(t20, i20, s16) {
    this.element = t20, this.type = 6, this._$AN = void 0, this._$AM = i20, this.options = s16;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(t20) {
    M(this, t20);
  }
};
var j = { M: h2, P: o3, A: n3, C: 1, L: N, R, D: d2, V: M, I: k, H, N: L, U: z, B: I, F: Z };
var B = t2.litHtmlPolyfillSupport;
B?.(S2, k), (t2.litHtmlVersions ??= []).push("3.3.2");
var D = (t20, i20, s16) => {
  const e31 = s16?.renderBefore ?? i20;
  let h11 = e31._$litPart$;
  if (void 0 === h11) {
    const t21 = s16?.renderBefore ?? null;
    e31._$litPart$ = h11 = new k(i20.insertBefore(c3(), t21), t21, void 0, s16 ?? {});
  }
  return h11._$AI(t20), h11;
};

// node_modules/lit-element/lit-element.js
var s3 = globalThis;
var i4 = class extends y {
  constructor() {
    super(...arguments), this.renderOptions = { host: this }, this._$Do = void 0;
  }
  createRenderRoot() {
    const t20 = super.createRenderRoot();
    return this.renderOptions.renderBefore ??= t20.firstChild, t20;
  }
  update(t20) {
    const r28 = this.render();
    this.hasUpdated || (this.renderOptions.isConnected = this.isConnected), super.update(t20), this._$Do = D(r28, this.renderRoot, this.renderOptions);
  }
  connectedCallback() {
    super.connectedCallback(), this._$Do?.setConnected(true);
  }
  disconnectedCallback() {
    super.disconnectedCallback(), this._$Do?.setConnected(false);
  }
  render() {
    return E;
  }
};
i4._$litElement$ = true, i4["finalized"] = true, s3.litElementHydrateSupport?.({ LitElement: i4 });
var o4 = s3.litElementPolyfillSupport;
o4?.({ LitElement: i4 });
(s3.litElementVersions ??= []).push("4.2.2");

// dist/primitives/base-element.js
var i5 = class i6 extends i4 {
};
i5.styles = i`
    :host {
      box-sizing: border-box;
    }

    :host *,
    :host *::before,
    :host *::after {
      box-sizing: inherit;
    }

    :host([hidden]) {
      display: none !important;
    }

    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border-width: 0;
    }
  `;
var o5 = i5;

// dist/primitives/pixel-font.js
var M2 = {
  A: [2, 5, 7, 5, 5],
  B: [6, 5, 6, 5, 6],
  C: [3, 4, 4, 4, 3],
  D: [6, 5, 5, 5, 6],
  E: [7, 4, 6, 4, 7],
  F: [7, 4, 6, 4, 4],
  G: [3, 4, 5, 5, 3],
  H: [5, 5, 7, 5, 5],
  I: [7, 2, 2, 2, 7],
  J: [1, 1, 1, 5, 2],
  K: [5, 5, 6, 5, 5],
  L: [4, 4, 4, 4, 7],
  M: [5, 7, 5, 5, 5],
  N: [5, 7, 7, 5, 5],
  O: [2, 5, 5, 5, 2],
  P: [6, 5, 6, 4, 4],
  Q: [2, 5, 5, 7, 3],
  R: [6, 5, 6, 5, 5],
  S: [3, 4, 2, 1, 6],
  T: [7, 2, 2, 2, 2],
  U: [5, 5, 5, 5, 2],
  V: [5, 5, 5, 2, 2],
  W: [5, 5, 5, 7, 5],
  X: [5, 5, 2, 5, 5],
  Y: [5, 5, 2, 2, 2],
  Z: [7, 1, 2, 4, 7],
  0: [7, 5, 5, 5, 7],
  1: [2, 6, 2, 2, 7],
  2: [6, 1, 2, 4, 7],
  3: [6, 1, 2, 1, 6],
  4: [5, 5, 7, 1, 1],
  5: [7, 4, 6, 1, 6],
  6: [3, 4, 7, 5, 7],
  7: [7, 1, 2, 2, 2],
  8: [7, 5, 2, 5, 7],
  9: [7, 5, 7, 1, 6],
  " ": [0, 0, 0, 0, 0],
  ":": [0, 2, 0, 2, 0],
  ".": [0, 0, 0, 0, 2],
  "%": [5, 1, 2, 4, 5],
  "/": [1, 1, 2, 4, 4],
  "-": [0, 0, 7, 0, 0],
  "!": [2, 2, 2, 0, 2],
  "+": [0, 2, 7, 2, 0]
};
function T2(h11, t20, c16, y8 = 1) {
  const i20 = new Uint8Array(t20 * c16), g15 = h11.toUpperCase(), s16 = 5, r28 = 3, l10 = 1, u13 = Math.max(0, Math.floor((c16 - s16) / 2));
  let e31 = 0;
  for (const b20 of g15) {
    const f24 = M2[b20];
    if (f24) {
      for (let o20 = 0; o20 < s16; o20++) {
        const x4 = f24[o20];
        for (let n14 = 0; n14 < r28; n14++)
          if (x4 >> r28 - 1 - n14 & 1) {
            const p9 = e31 + n14, a20 = u13 + o20;
            p9 < t20 && a20 < c16 && (i20[a20 * t20 + p9] = y8);
          }
      }
      if (e31 += r28 + l10, e31 >= t20) break;
    }
  }
  return i20;
}

// dist/primitives/pixel-renderers.js
function s4(o20, t20, n14, a20 = 1) {
  const i20 = new Uint8Array(t20 * n14);
  if (o20.length === 0 || n14 === 0 || t20 === 0) return i20;
  const r28 = Math.max(...o20), f24 = r28 > 0 ? o20.map((c16) => c16 / r28) : o20.map(() => 0), h11 = Math.max(0, f24.length - t20), e31 = f24.slice(h11), m18 = t20 - e31.length;
  for (let c16 = 0; c16 < e31.length; c16++) {
    if (e31[c16] === 0) continue;
    const d19 = Math.round(e31[c16] * (n14 - 1));
    for (let l10 = 0; l10 <= d19; l10++) {
      const g15 = n14 - 1 - l10;
      i20[g15 * t20 + (m18 + c16)] = a20;
    }
  }
  return i20;
}
function u3(o20, t20, n14, a20 = 1) {
  const i20 = new Uint8Array(t20 * n14);
  if (n14 === 0 || t20 === 0) return i20;
  const r28 = Math.max(0, Math.min(100, o20)), f24 = Math.round(r28 / 100 * t20), h11 = Math.floor(n14 / 2);
  for (let e31 = 0; e31 < f24; e31++)
    i20[h11 * t20 + e31] = a20;
  return i20;
}
function M3(o20, ...t20) {
  const n14 = new Uint8Array(o20);
  for (const a20 of t20) {
    const i20 = Math.min(n14.length, a20.length);
    for (let r28 = 0; r28 < i20; r28++)
      a20[r28] !== 0 && (n14[r28] = a20[r28]);
  }
  return n14;
}

// dist/primitives/terminal-parser.js
var a3 = {
  primary: "bh-t-primary",
  success: "bh-t-success",
  warning: "bh-t-warning",
  danger: "bh-t-danger",
  text: "bh-t-text",
  bright: "bh-t-bright",
  muted: "bh-t-muted",
  tertiary: "bh-t-tertiary",
  bold: "bh-t-bold"
};
function s5(r28) {
  return r28.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function c4(r28) {
  return r28.replace(/\{(\/?[a-zA-Z]*)\}/g, (e31, t20) => {
    if (t20 === "/")
      return "</span>";
    const n14 = a3[t20];
    return n14 ? `<span class="${n14}">` : `{${t20}}`;
  });
}
var i7 = /https?:\/\/[^\s<>"']+/g;
function l3(r28) {
  return r28.replace(i7, (e31) => `<a href="${e31}" target="_blank" rel="noopener noreferrer" part="link">${e31}</a>`);
}
function p3(r28) {
  const e31 = s5(r28), t20 = c4(e31);
  return l3(t20);
}

// dist/node_modules/@lit/context/lib/create-context.js
function e4(t20) {
  return t20;
}

// dist/primitives/terminal-context.js
var n4 = e4("bh-terminal-handler");

// node_modules/@lit/reactive-element/decorators/custom-element.js
var t3 = (t20) => (e31, o20) => {
  void 0 !== o20 ? o20.addInitializer(() => {
    customElements.define(t20, e31);
  }) : customElements.define(t20, e31);
};

// node_modules/@lit/reactive-element/decorators/property.js
var o6 = { attribute: true, type: String, converter: u, reflect: false, hasChanged: f };
var r4 = (t20 = o6, e31, r28) => {
  const { kind: n14, metadata: i20 } = r28;
  let s16 = globalThis.litPropertyMetadata.get(i20);
  if (void 0 === s16 && globalThis.litPropertyMetadata.set(i20, s16 = /* @__PURE__ */ new Map()), "setter" === n14 && ((t20 = Object.create(t20)).wrapped = true), s16.set(r28.name, t20), "accessor" === n14) {
    const { name: o20 } = r28;
    return { set(r29) {
      const n15 = e31.get.call(this);
      e31.set.call(this, r29), this.requestUpdate(o20, n15, t20, true, r29);
    }, init(e32) {
      return void 0 !== e32 && this.C(o20, void 0, t20, e32), e32;
    } };
  }
  if ("setter" === n14) {
    const { name: o20 } = r28;
    return function(r29) {
      const n15 = this[o20];
      e31.call(this, r29), this.requestUpdate(o20, n15, t20, true, r29);
    };
  }
  throw Error("Unsupported decorator location: " + n14);
};
function n5(t20) {
  return (e31, o20) => "object" == typeof o20 ? r4(t20, e31, o20) : ((t21, e32, o21) => {
    const r28 = e32.hasOwnProperty(o21);
    return e32.constructor.createProperty(o21, t21), r28 ? Object.getOwnPropertyDescriptor(e32, o21) : void 0;
  })(t20, e31, o20);
}

// node_modules/@lit/reactive-element/decorators/state.js
function r5(r28) {
  return n5({ ...r28, state: true, attribute: false });
}

// node_modules/@lit/reactive-element/decorators/base.js
var e5 = (e31, t20, c16) => (c16.configurable = true, c16.enumerable = true, Reflect.decorate && "object" != typeof t20 && Object.defineProperty(e31, t20, c16), c16);

// node_modules/@lit/reactive-element/decorators/query.js
function e6(e31, r28) {
  return (n14, s16, i20) => {
    const o20 = (t20) => t20.renderRoot?.querySelector(e31) ?? null;
    if (r28) {
      const { get: e32, set: r29 } = "object" == typeof s16 ? n14 : i20 ?? /* @__PURE__ */ (() => {
        const t20 = /* @__PURE__ */ Symbol();
        return { get() {
          return this[t20];
        }, set(e33) {
          this[t20] = e33;
        } };
      })();
      return e5(n14, s16, { get() {
        let t20 = e32.call(this);
        return void 0 === t20 && (t20 = o20(this), (null !== t20 || this.hasUpdated) && r29.call(this, t20)), t20;
      } });
    }
    return e5(n14, s16, { get() {
      return o20(this);
    } });
  };
}

// dist/atoms/avatar/bh-avatar.js
var g2 = Object.defineProperty;
var d3 = Object.getOwnPropertyDescriptor;
var e7 = (v22, i20, o20, a20) => {
  for (var r28 = a20 > 1 ? void 0 : a20 ? d3(i20, o20) : i20, h11 = v22.length - 1, l10; h11 >= 0; h11--)
    (l10 = v22[h11]) && (r28 = (a20 ? l10(i20, o20, r28) : l10(r28)) || r28);
  return a20 && r28 && g2(i20, o20, r28), r28;
};
var t4 = class extends o5 {
  constructor() {
    super(...arguments), this.size = "md", this.src = "", this.alt = "", this.initials = "", this._imgFailed = false;
  }
  render() {
    return this.src && !this._imgFailed ? b2`
        <img
          part="image"
          src=${this.src}
          alt=${this.alt || A}
          @error=${this._onImgError}
        />
      ` : this.initials ? b2`
        <span class="initials" part="initials" aria-label=${this.alt || A}>
          ${this.initials.slice(0, 2)}
        </span>
      ` : b2`
      <svg viewBox="0 0 24 24" aria-label=${this.alt || "User"}>
        <path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z"/>
      </svg>
    `;
  }
  _onImgError() {
    this._imgFailed = true;
  }
};
t4.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: var(--bh-radius-full);
        overflow: hidden;
        background: var(--bh-avatar-bg, var(--bh-color-secondary));
        color: var(--bh-avatar-color, var(--bh-color-secondary-text));
        font-family: var(--bh-font-sans);
        font-weight: var(--bh-font-semibold);
        flex-shrink: 0;
      }

      :host([size='sm']) {
        width: var(--bh-avatar-size, 2rem);
        height: var(--bh-avatar-size, 2rem);
        font-size: var(--bh-text-xs);
      }

      :host,
      :host([size='md']) {
        width: var(--bh-avatar-size, 2.5rem);
        height: var(--bh-avatar-size, 2.5rem);
        font-size: var(--bh-text-sm);
      }

      :host([size='lg']) {
        width: var(--bh-avatar-size, 3rem);
        height: var(--bh-avatar-size, 3rem);
        font-size: var(--bh-text-base);
      }

      img {
        width: 100%;
        height: 100%;
        object-fit: cover;
      }

      .initials {
        line-height: var(--bh-leading-none);
        text-transform: uppercase;
        user-select: none;
      }

      svg {
        width: 60%;
        height: 60%;
        fill: currentColor;
      }
    `
];
e7([
  n5({ reflect: true })
], t4.prototype, "size", 2);
e7([
  n5()
], t4.prototype, "src", 2);
e7([
  n5()
], t4.prototype, "alt", 2);
e7([
  n5()
], t4.prototype, "initials", 2);
e7([
  r5()
], t4.prototype, "_imgFailed", 2);
t4 = e7([
  t3("bh-avatar")
], t4);

// dist/atoms/badge/bh-badge.js
var d4 = Object.defineProperty;
var v2 = Object.getOwnPropertyDescriptor;
var b3 = (h11, e31, s16, t20) => {
  for (var r28 = t20 > 1 ? void 0 : t20 ? v2(e31, s16) : e31, o20 = h11.length - 1, n14; o20 >= 0; o20--)
    (n14 = h11[o20]) && (r28 = (t20 ? n14(e31, s16, r28) : n14(r28)) || r28);
  return t20 && r28 && d4(e31, s16, r28), r28;
};
var a4 = class extends o5 {
  constructor() {
    super(...arguments), this.variant = "default", this.size = "md";
  }
  render() {
    return b2`<span part="badge"><slot></slot></span>`;
  }
};
a4.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: inline-flex;
      }

      span {
        display: inline-flex;
        align-items: center;
        font-family: var(--bh-font-sans);
        font-weight: var(--bh-font-medium);
        line-height: var(--bh-leading-none);
        border-radius: var(--bh-radius-full);
        white-space: nowrap;
        background: var(--bh-badge-bg);
        color: var(--bh-badge-color);
      }

      /* Sizes */
      :host([size='sm']) span {
        font-size: var(--bh-text-xs);
        padding: var(--bh-spacing-0-5) var(--bh-spacing-2);
      }

      span,
      :host([size='md']) span {
        font-size: var(--bh-text-sm);
        padding: var(--bh-spacing-1) var(--bh-spacing-2-5);
      }

      /* Default */
      span,
      :host([variant='default']) span {
        --bh-badge-bg: var(--bh-color-secondary);
        --bh-badge-color: var(--bh-color-secondary-text);
      }

      /* Primary */
      :host([variant='primary']) span {
        --bh-badge-bg: var(--bh-color-primary);
        --bh-badge-color: var(--bh-color-primary-text);
      }

      /* Success */
      :host([variant='success']) span {
        --bh-badge-bg: var(--bh-color-success);
        --bh-badge-color: var(--bh-color-text-inverse);
      }

      /* Warning */
      :host([variant='warning']) span {
        --bh-badge-bg: var(--bh-color-warning);
        --bh-badge-color: var(--bh-color-text);
      }

      /* Danger */
      :host([variant='danger']) span {
        --bh-badge-bg: var(--bh-color-danger);
        --bh-badge-color: var(--bh-color-danger-text);
      }
    `
];
b3([
  n5({ reflect: true })
], a4.prototype, "variant", 2);
b3([
  n5({ reflect: true })
], a4.prototype, "size", 2);
a4 = b3([
  t3("bh-badge")
], a4);

// dist/atoms/button/bh-button.js
var v3 = Object.defineProperty;
var g3 = Object.getOwnPropertyDescriptor;
var r6 = (a20, e31, b20, s16) => {
  for (var o20 = s16 > 1 ? void 0 : s16 ? g3(e31, b20) : e31, i20 = a20.length - 1, l10; i20 >= 0; i20--)
    (l10 = a20[i20]) && (o20 = (s16 ? l10(e31, b20, o20) : l10(o20)) || o20);
  return s16 && o20 && v3(e31, b20, o20), o20;
};
var t5 = class extends o5 {
  constructor() {
    super(...arguments), this.variant = "primary", this.size = "md", this.disabled = false, this.iconOnly = false, this.label = "", this.type = "button";
  }
  render() {
    return b2`
      <button
        part="button"
        type=${this.type}
        ?disabled=${this.disabled}
        aria-disabled=${this.disabled ? "true" : A}
        aria-label=${this.label || A}
        @click=${this._handleClick}
      >
        <slot name="prefix"></slot>
        <span class="label"><slot>${this.label}</slot></span>
        <slot name="suffix"></slot>
      </button>
    `;
  }
  _handleClick(a20) {
    if (this.disabled) {
      a20.preventDefault(), a20.stopPropagation();
      return;
    }
    this.dispatchEvent(
      new CustomEvent("bh-click", {
        bubbles: true,
        composed: true,
        detail: { originalEvent: a20 }
      })
    );
  }
};
t5.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: inline-block;
      }

      button {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: var(--bh-spacing-2);
        border: var(--bh-border-1) solid transparent;
        cursor: pointer;
        font-family: var(--bh-font-sans);
        font-weight: var(--bh-font-medium);
        line-height: var(--bh-leading-none);
        text-decoration: none;
        transition: all var(--bh-transition-fast);
        border-radius: var(--bh-button-radius, var(--bh-radius-md));
        background: var(--bh-button-bg);
        color: var(--bh-button-color);
        border-color: var(--bh-button-border, transparent);
      }

      /* Sizes */
      :host([size='sm']) button {
        font-size: var(--bh-text-sm);
        padding: var(--bh-spacing-1-5) var(--bh-spacing-3);
      }

      button,
      :host([size='md']) button {
        font-size: var(--bh-text-base);
        padding: var(--bh-spacing-2) var(--bh-spacing-4);
      }

      :host([size='lg']) button {
        font-size: var(--bh-text-lg);
        padding: var(--bh-spacing-2-5) var(--bh-spacing-6);
      }

      /* Primary */
      :host([variant='primary']) button,
      button {
        --bh-button-bg: var(--bh-color-primary);
        --bh-button-color: var(--bh-color-primary-text);
      }

      :host([variant='primary']) button:hover:not(:disabled),
      button:hover:not(:disabled) {
        --bh-button-bg: var(--bh-color-primary-hover);
        transform: translateY(-1px);
      }

      :host([variant='primary']) button:active:not(:disabled),
      button:active:not(:disabled) {
        --bh-button-bg: var(--bh-color-primary-active);
        transform: translateY(0);
      }

      /* Secondary */
      :host([variant='secondary']) button {
        --bh-button-bg: var(--bh-color-secondary);
        --bh-button-color: var(--bh-color-secondary-text);
      }

      :host([variant='secondary']) button:hover:not(:disabled) {
        --bh-button-bg: var(--bh-color-secondary-hover);
        transform: translateY(-1px);
      }

      :host([variant='secondary']) button:active:not(:disabled) {
        --bh-button-bg: var(--bh-color-secondary-active);
        transform: translateY(0);
      }

      /* Ghost */
      :host([variant='ghost']) button {
        --bh-button-bg: transparent;
        --bh-button-color: var(--bh-color-text);
      }

      :host([variant='ghost']) button:hover:not(:disabled) {
        --bh-button-bg: var(--bh-color-secondary);
        transform: translateY(-1px);
      }

      :host([variant='ghost']) button:active:not(:disabled) {
        --bh-button-bg: var(--bh-color-secondary-hover);
        transform: translateY(0);
      }

      /* Danger */
      :host([variant='danger']) button {
        --bh-button-bg: var(--bh-color-danger);
        --bh-button-color: var(--bh-color-danger-text);
      }

      :host([variant='danger']) button:hover:not(:disabled) {
        --bh-button-bg: var(--bh-color-danger-hover);
        transform: translateY(-1px);
      }

      :host([variant='danger']) button:active:not(:disabled) {
        --bh-button-bg: var(--bh-color-danger-active);
        transform: translateY(0);
      }

      /* Focus */
      button:focus-visible {
        outline: 2px solid var(--bh-color-ring);
        outline-offset: 2px;
      }

      /* Icon-only */
      :host([icon-only]) button {
        gap: 0;
      }

      :host([icon-only][size='sm']) button {
        padding: var(--bh-spacing-1-5);
      }

      :host([icon-only]) button,
      :host([icon-only][size='md']) button {
        padding: var(--bh-spacing-2);
      }

      :host([icon-only][size='lg']) button {
        padding: var(--bh-spacing-2-5);
      }

      :host([icon-only]) .label {
        position: absolute;
        width: 1px;
        height: 1px;
        padding: 0;
        margin: -1px;
        overflow: hidden;
        clip: rect(0, 0, 0, 0);
        white-space: nowrap;
        border-width: 0;
      }

      /* Disabled */
      :host([disabled]) button {
        opacity: 0.5;
        cursor: not-allowed;
        pointer-events: none;
        transform: none;
      }
    `
];
r6([
  n5({ reflect: true })
], t5.prototype, "variant", 2);
r6([
  n5({ reflect: true })
], t5.prototype, "size", 2);
r6([
  n5({ type: Boolean, reflect: true })
], t5.prototype, "disabled", 2);
r6([
  n5({ type: Boolean, reflect: true, attribute: "icon-only" })
], t5.prototype, "iconOnly", 2);
r6([
  n5()
], t5.prototype, "label", 2);
r6([
  n5()
], t5.prototype, "type", 2);
t5 = r6([
  t3("bh-button")
], t5);

// dist/atoms/checkbox/bh-checkbox.js
var u4 = Object.defineProperty;
var m2 = Object.getOwnPropertyDescriptor;
var r7 = (o20, a20, n14, s16) => {
  for (var t20 = s16 > 1 ? void 0 : s16 ? m2(a20, n14) : a20, c16 = o20.length - 1, h11; c16 >= 0; c16--)
    (h11 = o20[c16]) && (t20 = (s16 ? h11(a20, n14, t20) : h11(t20)) || t20);
  return s16 && t20 && u4(a20, n14, t20), t20;
};
var e8 = class extends o5 {
  constructor() {
    super(...arguments), this.checked = false, this.indeterminate = false, this.disabled = false, this.value = "", this.name = "", this.label = "";
  }
  render() {
    const o20 = this.indeterminate ? b2`<svg viewBox="0 0 16 16"><path d="M3 8h10" stroke-linecap="round"/></svg>` : b2`<svg viewBox="0 0 16 16"><path d="M3 8l3.5 3.5L13 5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
    return b2`
      <label>
        <input
          type="checkbox"
          .checked=${this.checked}
          .indeterminate=${this.indeterminate}
          ?disabled=${this.disabled}
          name=${this.name || A}
          value=${this.value || A}
          aria-label=${this.label || A}
          @change=${this._handleChange}
        />
        <span class="checkbox" part="checkbox">${o20}</span>
        <span class="label" part="label"><slot>${this.label}</slot></span>
      </label>
    `;
  }
  _handleChange(o20) {
    const a20 = o20.target;
    this.checked = a20.checked, this.indeterminate = false, this.dispatchEvent(
      new CustomEvent("bh-change", {
        bubbles: true,
        composed: true,
        detail: { checked: this.checked }
      })
    );
  }
};
e8.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: inline-flex;
        align-items: center;
        gap: var(--bh-spacing-2);
        cursor: pointer;
      }

      :host([disabled]) {
        opacity: 0.5;
        cursor: not-allowed;
      }

      input {
        position: absolute;
        width: 1px;
        height: 1px;
        padding: 0;
        margin: -1px;
        overflow: hidden;
        clip: rect(0, 0, 0, 0);
        white-space: nowrap;
        border-width: 0;
      }

      .checkbox {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: var(--bh-checkbox-size, 1.25rem);
        height: var(--bh-checkbox-size, 1.25rem);
        border: var(--bh-border-2) solid var(--bh-color-border);
        border-radius: var(--bh-checkbox-radius, var(--bh-radius-sm));
        background: var(--bh-color-surface-raised);
        transition: background var(--bh-transition-fast),
                    border-color var(--bh-transition-fast);
        flex-shrink: 0;
      }

      .checkbox svg {
        width: 0.75rem;
        height: 0.75rem;
        stroke: var(--bh-color-primary-text);
        stroke-width: 3;
        fill: none;
        opacity: 0;
        transition: opacity var(--bh-transition-fast);
      }

      /* Checked */
      :host([checked]) .checkbox {
        background: var(--bh-color-primary);
        border-color: var(--bh-color-primary);
      }

      :host([checked]) .checkbox svg {
        opacity: 1;
      }

      /* Indeterminate */
      :host([indeterminate]) .checkbox {
        background: var(--bh-color-primary);
        border-color: var(--bh-color-primary);
      }

      :host([indeterminate]) .checkbox svg {
        opacity: 1;
      }

      /* Focus */
      input:focus-visible ~ .checkbox {
        outline: 2px solid var(--bh-color-ring);
        outline-offset: 2px;
      }

      /* Label */
      .label {
        font-family: var(--bh-font-sans);
        font-size: var(--bh-text-base);
        line-height: var(--bh-leading-normal);
        color: var(--bh-color-text);
        user-select: none;
      }
    `
];
r7([
  n5({ type: Boolean, reflect: true })
], e8.prototype, "checked", 2);
r7([
  n5({ type: Boolean, reflect: true })
], e8.prototype, "indeterminate", 2);
r7([
  n5({ type: Boolean, reflect: true })
], e8.prototype, "disabled", 2);
r7([
  n5()
], e8.prototype, "value", 2);
r7([
  n5()
], e8.prototype, "name", 2);
r7([
  n5()
], e8.prototype, "label", 2);
e8 = r7([
  t3("bh-checkbox")
], e8);

// dist/atoms/divider/bh-divider.js
var g4 = Object.defineProperty;
var b4 = Object.getOwnPropertyDescriptor;
var i8 = (h11, e31, o20, t20) => {
  for (var r28 = t20 > 1 ? void 0 : t20 ? b4(e31, o20) : e31, d19 = h11.length - 1, s16; d19 >= 0; d19--)
    (s16 = h11[d19]) && (r28 = (t20 ? s16(e31, o20, r28) : s16(r28)) || r28);
  return t20 && r28 && g4(e31, o20, r28), r28;
};
var a5 = class extends o5 {
  constructor() {
    super(...arguments), this.vertical = false, this.spacing = "md", this.gradient = false;
  }
  render() {
    return b2`
      <hr part="divider" aria-hidden="true" />
      <div class="vertical" part="divider" aria-hidden="true"></div>
    `;
  }
};
a5.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }

      hr {
        border: none;
        height: 1px;
        background: var(--bh-divider-color, var(--bh-color-border-muted));
        box-shadow: var(--bh-divider-shadow, var(--bh-shadow-emboss));
        margin: 0;
      }

      /* Spacing */
      :host([spacing='sm']) {
        padding: var(--bh-spacing-2) 0;
      }

      :host,
      :host([spacing='md']) {
        padding: var(--bh-spacing-4) 0;
      }

      :host([spacing='lg']) {
        padding: var(--bh-spacing-8) 0;
      }

      /* Vertical */
      :host([vertical]) {
        display: inline-block;
        height: 100%;
        padding: 0;
      }

      :host([vertical]) hr {
        display: none;
      }

      .vertical {
        display: none;
        width: 1px;
        height: 100%;
        background: var(--bh-divider-color, var(--bh-color-border-muted));
        box-shadow: var(--bh-divider-shadow, var(--bh-shadow-emboss));
      }

      :host([vertical]) .vertical {
        display: block;
      }

      :host([vertical][spacing='sm']) {
        padding: 0 var(--bh-spacing-2);
      }

      :host([vertical][spacing='md']),
      :host([vertical]) {
        padding: 0 var(--bh-spacing-4);
      }

      :host([vertical][spacing='lg']) {
        padding: 0 var(--bh-spacing-8);
      }

      /* Gradient mode */
      :host([gradient]) hr {
        height: 2px;
        background: var(
          --bh-divider-gradient,
          linear-gradient(to right, var(--bh-color-primary), var(--bh-color-border-muted) 40%, transparent)
        );
        box-shadow: none;
      }

      :host([gradient][vertical]) .vertical {
        width: 2px;
        background: var(
          --bh-divider-gradient,
          linear-gradient(to bottom, var(--bh-color-primary), var(--bh-color-border-muted) 40%, transparent)
        );
        box-shadow: none;
      }
    `
];
i8([
  n5({ type: Boolean, reflect: true })
], a5.prototype, "vertical", 2);
i8([
  n5({ reflect: true })
], a5.prototype, "spacing", 2);
i8([
  n5({ type: Boolean, reflect: true })
], a5.prototype, "gradient", 2);
a5 = i8([
  t3("bh-divider")
], a5);

// node_modules/lit-html/directive.js
var t6 = { ATTRIBUTE: 1, CHILD: 2, PROPERTY: 3, BOOLEAN_ATTRIBUTE: 4, EVENT: 5, ELEMENT: 6 };
var e9 = (t20) => (...e31) => ({ _$litDirective$: t20, values: e31 });
var i9 = class {
  constructor(t20) {
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AT(t20, e31, i20) {
    this._$Ct = t20, this._$AM = e31, this._$Ci = i20;
  }
  _$AS(t20, e31) {
    return this.update(t20, e31);
  }
  update(t20, e31) {
    return this.render(...e31);
  }
};

// node_modules/lit-html/directives/unsafe-html.js
var e10 = class extends i9 {
  constructor(i20) {
    if (super(i20), this.it = A, i20.type !== t6.CHILD) throw Error(this.constructor.directiveName + "() can only be used in child bindings");
  }
  render(r28) {
    if (r28 === A || null == r28) return this._t = void 0, this.it = r28;
    if (r28 === E) return r28;
    if ("string" != typeof r28) throw Error(this.constructor.directiveName + "() called with a non-string value");
    if (r28 === this.it) return this._t;
    this.it = r28;
    const s16 = [r28];
    return s16.raw = s16, this._t = { _$litType$: this.constructor.resultType, strings: s16, values: [] };
  }
};
e10.directiveName = "unsafeHTML", e10.resultType = 1;
var o7 = e9(e10);

// node_modules/lit-html/directives/unsafe-svg.js
var t7 = class extends e10 {
};
t7.directiveName = "unsafeSVG", t7.resultType = 2;
var o8 = e9(t7);

// dist/atoms/icon/bh-icon.js
var f3 = Object.defineProperty;
var b5 = Object.getOwnPropertyDescriptor;
var n6 = (t20, r28, i20, o20) => {
  for (var s16 = o20 > 1 ? void 0 : o20 ? b5(r28, i20) : r28, a20 = t20.length - 1, l10; a20 >= 0; a20--)
    (l10 = t20[a20]) && (s16 = (o20 ? l10(r28, i20, s16) : l10(s16)) || s16);
  return o20 && s16 && f3(r28, i20, s16), s16;
};
var c5 = /* @__PURE__ */ new Map();
var e11 = class extends o5 {
  constructor() {
    super(...arguments), this.name = "", this.size = "md", this.label = "";
  }
  static register(t20, r28) {
    c5.set(t20, r28);
  }
  static getIcon(t20) {
    return c5.get(t20);
  }
  render() {
    const t20 = c5.get(this.name), r28 = this.label ? A : "true", i20 = this.label ? "img" : A;
    return b2`
      <svg
        part="svg"
        viewBox="0 0 24 24"
        aria-hidden=${r28}
        role=${i20}
        aria-label=${this.label || A}
      >
        ${t20 ? o8(t20) : A}
      </svg>
    `;
  }
};
e11.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: var(--bh-icon-size, 1.25em);
        height: var(--bh-icon-size, 1.25em);
        color: inherit;
        flex-shrink: 0;
      }

      :host([size='sm']) {
        --bh-icon-size: 1rem;
      }

      :host([size='md']) {
        --bh-icon-size: 1.25rem;
      }

      :host([size='lg']) {
        --bh-icon-size: 1.5rem;
      }

      svg {
        width: 100%;
        height: 100%;
        fill: none;
        stroke: currentColor;
        stroke-width: 2;
        stroke-linecap: round;
        stroke-linejoin: round;
      }
    `
];
n6([
  n5({ reflect: true })
], e11.prototype, "name", 2);
n6([
  n5({ reflect: true })
], e11.prototype, "size", 2);
n6([
  n5()
], e11.prototype, "label", 2);
e11 = n6([
  t3("bh-icon")
], e11);
e11.register("x", '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>');
e11.register("check", '<path d="M20 6 9 17l-5-5"/>');
e11.register("plus", '<path d="M5 12h14"/><path d="M12 5v14"/>');
e11.register("minus", '<path d="M5 12h14"/>');
e11.register("search", '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>');
e11.register("chevron-down", '<path d="m6 9 6 6 6-6"/>');
e11.register("chevron-up", '<path d="m18 15-6-6-6 6"/>');
e11.register("chevron-left", '<path d="m15 18-6-6 6-6"/>');
e11.register("chevron-right", '<path d="m9 18 6-6-6-6"/>');
e11.register("menu", '<path d="M4 12h16"/><path d="M4 6h16"/><path d="M4 18h16"/>');

// node_modules/lit-html/directive-helpers.js
var { I: t8 } = j;
var i10 = (o20) => o20;
var r8 = (o20) => void 0 === o20.strings;
var s6 = () => document.createComment("");
var v4 = (o20, n14, e31) => {
  const l10 = o20._$AA.parentNode, d19 = void 0 === n14 ? o20._$AB : n14._$AA;
  if (void 0 === e31) {
    const i20 = l10.insertBefore(s6(), d19), n15 = l10.insertBefore(s6(), d19);
    e31 = new t8(i20, n15, o20, o20.options);
  } else {
    const t20 = e31._$AB.nextSibling, n15 = e31._$AM, c16 = n15 !== o20;
    if (c16) {
      let t21;
      e31._$AQ?.(o20), e31._$AM = o20, void 0 !== e31._$AP && (t21 = o20._$AU) !== n15._$AU && e31._$AP(t21);
    }
    if (t20 !== d19 || c16) {
      let o21 = e31._$AA;
      for (; o21 !== t20; ) {
        const t21 = i10(o21).nextSibling;
        i10(l10).insertBefore(o21, d19), o21 = t21;
      }
    }
  }
  return e31;
};
var u5 = (o20, t20, i20 = o20) => (o20._$AI(t20, i20), o20);
var m3 = {};
var p4 = (o20, t20 = m3) => o20._$AH = t20;
var M4 = (o20) => o20._$AH;
var h3 = (o20) => {
  o20._$AR(), o20._$AA.remove();
};

// node_modules/lit-html/directives/live.js
var l4 = e9(class extends i9 {
  constructor(r28) {
    if (super(r28), r28.type !== t6.PROPERTY && r28.type !== t6.ATTRIBUTE && r28.type !== t6.BOOLEAN_ATTRIBUTE) throw Error("The `live` directive is not allowed on child or event bindings");
    if (!r8(r28)) throw Error("`live` bindings can only contain a single expression");
  }
  render(r28) {
    return r28;
  }
  update(i20, [t20]) {
    if (t20 === E || t20 === A) return t20;
    const o20 = i20.element, l10 = i20.name;
    if (i20.type === t6.PROPERTY) {
      if (t20 === o20[l10]) return E;
    } else if (i20.type === t6.BOOLEAN_ATTRIBUTE) {
      if (!!t20 === o20.hasAttribute(l10)) return E;
    } else if (i20.type === t6.ATTRIBUTE && o20.getAttribute(l10) === t20 + "") return E;
    return p4(i20), t20;
  }
});

// dist/atoms/input/bh-input.js
var f4 = Object.defineProperty;
var g5 = Object.getOwnPropertyDescriptor;
var r9 = (s16, a20, l10, i20) => {
  for (var o20 = i20 > 1 ? void 0 : i20 ? g5(a20, l10) : a20, n14 = s16.length - 1, h11; n14 >= 0; n14--)
    (h11 = s16[n14]) && (o20 = (i20 ? h11(a20, l10, o20) : h11(o20)) || o20);
  return i20 && o20 && f4(a20, l10, o20), o20;
};
var e12 = class extends o5 {
  constructor() {
    super(...arguments), this.size = "md", this.type = "text", this.value = "", this.placeholder = "", this.name = "", this.label = "", this.disabled = false, this.readonly = false, this.required = false, this.error = false;
  }
  render() {
    return b2`
      <div class="wrapper" part="wrapper">
        <span class="prefix"><slot name="prefix"></slot></span>
        <input
          part="input"
          type=${this.type}
          .value=${l4(this.value)}
          placeholder=${this.placeholder || A}
          name=${this.name || A}
          aria-label=${this.label || A}
          ?disabled=${this.disabled}
          ?readonly=${this.readonly}
          ?required=${this.required}
          aria-invalid=${this.error ? "true" : A}
          @input=${this._handleInput}
          @change=${this._handleChange}
        />
        <span class="suffix"><slot name="suffix"></slot></span>
      </div>
    `;
  }
  _handleInput(s16) {
    const a20 = s16.target;
    this.value = a20.value, this.dispatchEvent(
      new CustomEvent("bh-input", {
        bubbles: true,
        composed: true,
        detail: { value: this.value }
      })
    );
  }
  _handleChange(s16) {
    const a20 = s16.target;
    this.value = a20.value, this.dispatchEvent(
      new CustomEvent("bh-change", {
        bubbles: true,
        composed: true,
        detail: { value: this.value }
      })
    );
  }
};
e12.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }

      .wrapper {
        display: flex;
        align-items: center;
        width: 100%;
        background: var(--bh-input-bg, var(--bh-color-surface-raised));
        border: var(--bh-border-1) solid var(--bh-input-border, var(--bh-color-border));
        border-radius: var(--bh-input-radius, var(--bh-radius-md));
        box-shadow: var(--bh-shadow-inset);
        transition: all var(--bh-transition-fast);
      }

      input {
        flex: 1;
        min-width: 0;
        font-family: var(--bh-font-sans);
        line-height: var(--bh-leading-normal);
        color: var(--bh-input-color, var(--bh-color-text));
        background: transparent;
        border: none;
        outline: none;
      }

      input::placeholder {
        color: var(--bh-color-text-muted);
      }

      /* Slots */
      .prefix,
      .suffix {
        display: flex;
        align-items: center;
        flex-shrink: 0;
        color: var(--bh-color-text-muted);
      }

      /* Sizes — wrapper padding */
      :host([size='sm']) .wrapper {
        font-size: var(--bh-text-sm);
        gap: var(--bh-spacing-1-5);
        padding: var(--bh-spacing-1-5) var(--bh-spacing-3);
      }

      .wrapper,
      :host([size='md']) .wrapper {
        font-size: var(--bh-text-base);
        gap: var(--bh-spacing-2);
        padding: var(--bh-spacing-2) var(--bh-spacing-4);
      }

      :host([size='lg']) .wrapper {
        font-size: var(--bh-text-lg);
        gap: var(--bh-spacing-2);
        padding: var(--bh-spacing-2-5) var(--bh-spacing-6);
      }

      /* Sizes — input font inherits from wrapper */
      input {
        font-size: inherit;
      }

      /* Focus */
      .wrapper:focus-within {
        border-color: var(--bh-color-ring);
        box-shadow: 0 0 0 1px var(--bh-color-ring);
      }

      /* Error */
      :host([error]) .wrapper {
        border-color: var(--bh-color-danger);
      }

      :host([error]) .wrapper:focus-within {
        border-color: var(--bh-color-danger);
        box-shadow: 0 0 0 1px var(--bh-color-danger);
      }

      /* Disabled */
      :host([disabled]) .wrapper {
        opacity: 0.5;
        cursor: not-allowed;
      }

      :host([disabled]) input {
        cursor: not-allowed;
      }

      /* Readonly */
      :host([readonly]) .wrapper {
        background: var(--bh-color-surface);
      }
    `
];
r9([
  n5({ reflect: true })
], e12.prototype, "size", 2);
r9([
  n5()
], e12.prototype, "type", 2);
r9([
  n5()
], e12.prototype, "value", 2);
r9([
  n5()
], e12.prototype, "placeholder", 2);
r9([
  n5()
], e12.prototype, "name", 2);
r9([
  n5()
], e12.prototype, "label", 2);
r9([
  n5({ type: Boolean, reflect: true })
], e12.prototype, "disabled", 2);
r9([
  n5({ type: Boolean, reflect: true })
], e12.prototype, "readonly", 2);
r9([
  n5({ type: Boolean, reflect: true })
], e12.prototype, "required", 2);
r9([
  n5({ type: Boolean, reflect: true })
], e12.prototype, "error", 2);
e12 = r9([
  t3("bh-input")
], e12);

// dist/atoms/led/bh-led.js
var m4 = Object.defineProperty;
var g6 = Object.getOwnPropertyDescriptor;
var r10 = (i20, s16, t20, l10) => {
  for (var e31 = l10 > 1 ? void 0 : l10 ? g6(s16, t20) : s16, p9 = i20.length - 1, h11; p9 >= 0; p9--)
    (h11 = i20[p9]) && (e31 = (l10 ? h11(s16, t20, e31) : h11(e31)) || e31);
  return l10 && e31 && m4(s16, t20, e31), e31;
};
var o9 = class extends o5 {
  constructor() {
    super(...arguments), this.color = "success", this.pulse = false, this.size = "md", this.label = "";
  }
  render() {
    return b2`
      <span
        part="led"
        role="status"
        aria-label=${this.label || A}
      ></span>
    `;
  }
};
o9.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: inline-flex;
        align-items: center;
        justify-content: center;
      }

      span {
        display: block;
        width: var(--bh-led-size, 8px);
        height: var(--bh-led-size, 8px);
        border-radius: var(--bh-radius-full);
        background: var(--bh-led-color);
        box-shadow: 0 0 6px var(--bh-led-glow);
      }

      /* Sizes */
      :host([size='sm']) span {
        --bh-led-size: 6px;
      }

      span,
      :host([size='md']) span {
        --bh-led-size: 8px;
      }

      /* Colors */
      span,
      :host([color='success']) span {
        --bh-led-color: var(--bh-color-success);
        --bh-led-glow: var(--bh-color-success-dim, rgba(42, 157, 78, 0.15));
      }

      :host([color='warning']) span {
        --bh-led-color: var(--bh-color-warning);
        --bh-led-glow: rgba(245, 158, 11, 0.25);
      }

      :host([color='danger']) span {
        --bh-led-color: var(--bh-color-danger);
        --bh-led-glow: rgba(220, 38, 38, 0.25);
      }

      :host([color='primary']) span {
        --bh-led-color: var(--bh-color-primary);
        --bh-led-glow: var(--bh-color-primary-glow, rgba(255, 107, 53, 0.12));
      }

      /* Pulse animation */
      :host([pulse]) span {
        animation: led-pulse 2s ease-in-out infinite;
      }

      @keyframes led-pulse {
        0%, 100% {
          opacity: 1;
          box-shadow: 0 0 6px var(--bh-led-glow);
        }
        50% {
          opacity: 0.6;
          box-shadow: 0 0 12px var(--bh-led-glow);
        }
      }
    `
];
r10([
  n5({ reflect: true })
], o9.prototype, "color", 2);
r10([
  n5({ type: Boolean, reflect: true })
], o9.prototype, "pulse", 2);
r10([
  n5({ reflect: true })
], o9.prototype, "size", 2);
r10([
  n5()
], o9.prototype, "label", 2);
o9 = r10([
  t3("bh-led")
], o9);

// dist/atoms/link/bh-link.js
var d5 = Object.defineProperty;
var b6 = Object.getOwnPropertyDescriptor;
var n7 = (r28, o20, s16, i20) => {
  for (var e31 = i20 > 1 ? void 0 : i20 ? b6(o20, s16) : o20, h11 = r28.length - 1, c16; h11 >= 0; h11--)
    (c16 = r28[h11]) && (e31 = (i20 ? c16(o20, s16, e31) : c16(e31)) || e31);
  return i20 && e31 && d5(o20, s16, e31), e31;
};
var t9 = class extends o5 {
  constructor() {
    super(...arguments), this.href = "", this.target = "", this.variant = "default", this.external = false;
  }
  render() {
    const r28 = this.external ? "_blank" : this.target, o20 = this.external ? "noopener noreferrer" : void 0;
    return b2`
      <a
        part="link"
        href=${this.href || A}
        target=${r28 || A}
        rel=${o20 || A}
        @click=${this._handleClick}
      >
        <slot></slot>${this.external ? b2`<span class="external-icon"><svg viewBox="0 0 16 16"><path d="M6 3h7v7"/><path d="M13 3L6.5 9.5"/></svg></span>` : A}
      </a>
    `;
  }
  _handleClick(r28) {
    this.dispatchEvent(
      new CustomEvent("bh-click", {
        bubbles: true,
        composed: true,
        detail: { originalEvent: r28 }
      })
    );
  }
};
t9.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: inline;
      }

      a {
        color: var(--bh-link-color, var(--bh-color-link));
        font-family: inherit;
        font-size: inherit;
        line-height: inherit;
        text-decoration: underline;
        text-decoration-color: transparent;
        text-underline-offset: 0.15em;
        transition: all var(--bh-transition-fast);
        cursor: pointer;
      }

      a:hover {
        color: var(--bh-color-link-hover);
        text-decoration-color: currentColor;
      }

      a:focus-visible {
        outline: 2px solid var(--bh-color-ring);
        outline-offset: 2px;
        border-radius: var(--bh-radius-sm);
      }

      /* Variants */
      :host([variant='muted']) a {
        --bh-link-color: var(--bh-color-link-subtle);
      }

      :host([variant='muted']) a:hover {
        color: var(--bh-color-link-subtle-hover);
      }

      :host([variant='accent']) a {
        --bh-link-color: var(--bh-color-primary);
        font-weight: var(--bh-font-medium);
      }

      /* External icon */
      .external-icon {
        display: inline-block;
        width: 0.75em;
        height: 0.75em;
        margin-left: 0.2em;
        vertical-align: baseline;
      }

      .external-icon svg {
        width: 100%;
        height: 100%;
        fill: none;
        stroke: currentColor;
        stroke-width: 2;
        stroke-linecap: round;
        stroke-linejoin: round;
      }
    `
];
n7([
  n5()
], t9.prototype, "href", 2);
n7([
  n5()
], t9.prototype, "target", 2);
n7([
  n5({ reflect: true })
], t9.prototype, "variant", 2);
n7([
  n5({ type: Boolean })
], t9.prototype, "external", 2);
t9 = n7([
  t3("bh-link")
], t9);

// dist/atoms/progress/bh-progress.js
var d6 = Object.defineProperty;
var v5 = Object.getOwnPropertyDescriptor;
var t10 = (s16, i20, n14, o20) => {
  for (var e31 = o20 > 1 ? void 0 : o20 ? v5(i20, n14) : i20, h11 = s16.length - 1, l10; h11 >= 0; h11--)
    (l10 = s16[h11]) && (e31 = (o20 ? l10(i20, n14, e31) : l10(e31)) || e31);
  return o20 && e31 && d6(i20, n14, e31), e31;
};
var r11 = class extends o5 {
  constructor() {
    super(...arguments), this.value = 0, this.max = 100, this.indeterminate = false, this.size = "md", this.variant = "default", this.label = "Progress";
  }
  render() {
    const s16 = this.indeterminate ? void 0 : Math.min(100, Math.max(0, this.value / this.max * 100));
    return b2`
      <div
        class="track"
        part="track"
        role="progressbar"
        aria-label=${this.label}
        aria-valuenow=${this.indeterminate ? "" : this.value}
        aria-valuemin="0"
        aria-valuemax=${this.max}
      >
        <div
          class="bar"
          part="bar"
          style=${this.indeterminate ? "" : `width: ${s16}%`}
        ></div>
      </div>
    `;
  }
};
r11.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
        width: 100%;
      }

      .track {
        width: 100%;
        border-radius: var(--bh-radius-full);
        background: var(--bh-progress-track, var(--bh-color-secondary));
        overflow: hidden;
      }

      :host([size='sm']) .track { height: 0.25rem; }
      .track, :host([size='md']) .track { height: 0.5rem; }
      :host([size='lg']) .track { height: 0.75rem; }

      .bar {
        height: 100%;
        border-radius: var(--bh-radius-full);
        background: var(--bh-progress-color, var(--bh-color-primary));
        transition: width var(--bh-transition-normal);
      }

      /* Variants */
      :host([variant='success']) .bar { --bh-progress-color: var(--bh-color-success); }
      :host([variant='warning']) .bar { --bh-progress-color: var(--bh-color-warning); }
      :host([variant='danger']) .bar { --bh-progress-color: var(--bh-color-danger); }

      /* Indeterminate */
      :host([indeterminate]) .bar {
        width: 40% !important;
        animation: indeterminate 1.5s var(--bh-ease-in-out) infinite;
      }

      @keyframes indeterminate {
        0% { transform: translateX(-100%); }
        100% { transform: translateX(350%); }
      }
    `
];
t10([
  n5({ type: Number })
], r11.prototype, "value", 2);
t10([
  n5({ type: Number })
], r11.prototype, "max", 2);
t10([
  n5({ type: Boolean, reflect: true })
], r11.prototype, "indeterminate", 2);
t10([
  n5({ reflect: true })
], r11.prototype, "size", 2);
t10([
  n5({ reflect: true })
], r11.prototype, "variant", 2);
t10([
  n5()
], r11.prototype, "label", 2);
r11 = t10([
  t3("bh-progress")
], r11);

// dist/atoms/radio/bh-radio.js
var v6 = Object.defineProperty;
var f5 = Object.getOwnPropertyDescriptor;
var a6 = (d19, o20, i20, s16) => {
  for (var r28 = s16 > 1 ? void 0 : s16 ? f5(o20, i20) : o20, l10 = d19.length - 1, n14; l10 >= 0; l10--)
    (n14 = d19[l10]) && (r28 = (s16 ? n14(o20, i20, r28) : n14(r28)) || r28);
  return s16 && r28 && v6(o20, i20, r28), r28;
};
var e13 = class extends o5 {
  constructor() {
    super(...arguments), this.checked = false, this.disabled = false, this.value = "", this.name = "", this.label = "";
  }
  render() {
    return b2`
      <label>
        <input
          type="radio"
          .checked=${this.checked}
          ?disabled=${this.disabled}
          name=${this.name || A}
          value=${this.value || A}
          aria-label=${this.label || A}
          @change=${this._handleChange}
        />
        <span class="radio" part="radio">
          <span class="dot"></span>
        </span>
        <span class="label" part="label"><slot>${this.label}</slot></span>
      </label>
    `;
  }
  _handleChange() {
    this.checked = true, this.dispatchEvent(
      new CustomEvent("bh-change", {
        bubbles: true,
        composed: true,
        detail: { checked: true, value: this.value }
      })
    );
  }
};
e13.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: inline-flex;
        align-items: center;
        gap: var(--bh-spacing-2);
        cursor: pointer;
      }

      :host([disabled]) {
        opacity: 0.5;
        cursor: not-allowed;
      }

      input {
        position: absolute;
        width: 1px;
        height: 1px;
        padding: 0;
        margin: -1px;
        overflow: hidden;
        clip: rect(0, 0, 0, 0);
        white-space: nowrap;
        border-width: 0;
      }

      .radio {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: var(--bh-radio-size, 1.25rem);
        height: var(--bh-radio-size, 1.25rem);
        border: var(--bh-border-2) solid var(--bh-color-border);
        border-radius: var(--bh-radius-full);
        background: var(--bh-color-surface-raised);
        transition: border-color var(--bh-transition-fast);
        flex-shrink: 0;
      }

      .dot {
        width: 0.5rem;
        height: 0.5rem;
        border-radius: var(--bh-radius-full);
        background: var(--bh-color-primary-text);
        opacity: 0;
        transform: scale(0);
        transition: opacity var(--bh-transition-fast),
                    transform var(--bh-transition-fast);
      }

      /* Checked */
      :host([checked]) .radio {
        background: var(--bh-color-primary);
        border-color: var(--bh-color-primary);
      }

      :host([checked]) .dot {
        opacity: 1;
        transform: scale(1);
      }

      /* Focus */
      input:focus-visible ~ .radio {
        outline: 2px solid var(--bh-color-ring);
        outline-offset: 2px;
      }

      /* Label */
      .label {
        font-family: var(--bh-font-sans);
        font-size: var(--bh-text-base);
        line-height: var(--bh-leading-normal);
        color: var(--bh-color-text);
        user-select: none;
      }
    `
];
a6([
  n5({ type: Boolean, reflect: true })
], e13.prototype, "checked", 2);
a6([
  n5({ type: Boolean, reflect: true })
], e13.prototype, "disabled", 2);
a6([
  n5()
], e13.prototype, "value", 2);
a6([
  n5()
], e13.prototype, "name", 2);
a6([
  n5()
], e13.prototype, "label", 2);
e13 = a6([
  t3("bh-radio")
], e13);

// dist/atoms/select/bh-select.js
var u6 = Object.defineProperty;
var g7 = Object.getOwnPropertyDescriptor;
var t11 = (r28, o20, p9, i20) => {
  for (var s16 = i20 > 1 ? void 0 : i20 ? g7(o20, p9) : o20, h11 = r28.length - 1, d19; h11 >= 0; h11--)
    (d19 = r28[h11]) && (s16 = (i20 ? d19(o20, p9, s16) : d19(s16)) || s16);
  return i20 && s16 && u6(o20, p9, s16), s16;
};
var e14 = class extends o5 {
  constructor() {
    super(...arguments), this.size = "md", this.value = "", this.name = "", this.label = "", this.placeholder = "", this.options = [], this.optionGroups = [], this.disabled = false, this.required = false, this.error = false;
  }
  render() {
    return b2`
      <div class="wrapper" part="wrapper">
        <span class="prefix"><slot name="prefix"></slot></span>
        <select
          part="select"
          name=${this.name || A}
          aria-label=${this.label || A}
          ?disabled=${this.disabled}
          ?required=${this.required}
          aria-invalid=${this.error ? "true" : A}
          @change=${this._handleChange}
        >
          ${this.placeholder ? b2`<option value="" disabled ?selected=${!this.value}>${this.placeholder}</option>` : A}
          ${this.optionGroups.length > 0 ? this.optionGroups.map(
      (r28) => b2`
                  <optgroup label=${r28.label}>
                    ${r28.options.map(
        (o20) => b2`
                        <option
                          value=${o20.value}
                          ?disabled=${o20.disabled}
                          ?selected=${o20.value === this.value}
                        >${o20.label}</option>
                      `
      )}
                  </optgroup>
                `
    ) : this.options.map(
      (r28) => b2`
                  <option
                    value=${r28.value}
                    ?disabled=${r28.disabled}
                    ?selected=${r28.value === this.value}
                  >${r28.label}</option>
                `
    )}
        </select>
        <span class="chevron">
          <svg viewBox="0 0 16 16"><path d="M4 6l4 4 4-4"/></svg>
        </span>
      </div>
    `;
  }
  _handleChange(r28) {
    const o20 = r28.target;
    this.value = o20.value, this.dispatchEvent(
      new CustomEvent("bh-change", {
        bubbles: true,
        composed: true,
        detail: { value: this.value }
      })
    );
  }
};
e14.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }

      .wrapper {
        display: flex;
        align-items: center;
        width: 100%;
        background: var(--bh-select-bg, var(--bh-color-surface-raised));
        border: var(--bh-border-1) solid var(--bh-select-border, var(--bh-color-border));
        border-radius: var(--bh-select-radius, var(--bh-radius-md));
        box-shadow: var(--bh-shadow-inset);
        transition: all var(--bh-transition-fast);
        cursor: pointer;
      }

      select {
        flex: 1;
        min-width: 0;
        font-family: var(--bh-font-sans);
        line-height: var(--bh-leading-normal);
        color: var(--bh-select-color, var(--bh-color-text));
        background: transparent;
        border: none;
        outline: none;
        cursor: pointer;
        appearance: none;
        -webkit-appearance: none;
      }

      /* Prefix slot */
      .prefix {
        display: flex;
        align-items: center;
        flex-shrink: 0;
        color: var(--bh-color-text-muted);
      }

      /* Chevron indicator */
      .chevron {
        display: flex;
        align-items: center;
        flex-shrink: 0;
        color: var(--bh-color-text-muted);
        pointer-events: none;
      }

      .chevron svg {
        width: 1em;
        height: 1em;
        fill: none;
        stroke: currentColor;
        stroke-width: 2;
        stroke-linecap: round;
        stroke-linejoin: round;
      }

      /* Sizes */
      :host([size='sm']) .wrapper {
        font-size: var(--bh-text-sm);
        gap: var(--bh-spacing-1-5);
        padding: var(--bh-spacing-1-5) var(--bh-spacing-3);
      }

      .wrapper,
      :host([size='md']) .wrapper {
        font-size: var(--bh-text-base);
        gap: var(--bh-spacing-2);
        padding: var(--bh-spacing-2) var(--bh-spacing-4);
      }

      :host([size='lg']) .wrapper {
        font-size: var(--bh-text-lg);
        gap: var(--bh-spacing-2);
        padding: var(--bh-spacing-2-5) var(--bh-spacing-6);
      }

      select {
        font-size: inherit;
      }

      /* Focus */
      .wrapper:focus-within {
        border-color: var(--bh-color-ring);
        box-shadow: 0 0 0 1px var(--bh-color-ring);
      }

      /* Error */
      :host([error]) .wrapper {
        border-color: var(--bh-color-danger);
      }

      :host([error]) .wrapper:focus-within {
        border-color: var(--bh-color-danger);
        box-shadow: 0 0 0 1px var(--bh-color-danger);
      }

      /* Disabled */
      :host([disabled]) .wrapper {
        opacity: 0.5;
        cursor: not-allowed;
      }

      :host([disabled]) select {
        cursor: not-allowed;
      }

      /* Placeholder styling */
      select:invalid {
        color: var(--bh-color-text-muted);
      }
    `
];
t11([
  n5({ reflect: true })
], e14.prototype, "size", 2);
t11([
  n5()
], e14.prototype, "value", 2);
t11([
  n5()
], e14.prototype, "name", 2);
t11([
  n5()
], e14.prototype, "label", 2);
t11([
  n5()
], e14.prototype, "placeholder", 2);
t11([
  n5({ type: Array })
], e14.prototype, "options", 2);
t11([
  n5({ type: Array, attribute: "option-groups" })
], e14.prototype, "optionGroups", 2);
t11([
  n5({ type: Boolean, reflect: true })
], e14.prototype, "disabled", 2);
t11([
  n5({ type: Boolean, reflect: true })
], e14.prototype, "required", 2);
t11([
  n5({ type: Boolean, reflect: true })
], e14.prototype, "error", 2);
e14 = t11([
  t3("bh-select")
], e14);

// dist/atoms/skeleton/bh-skeleton.js
var v7 = Object.defineProperty;
var b7 = Object.getOwnPropertyDescriptor;
var i11 = (r28, s16, a20, o20) => {
  for (var t20 = o20 > 1 ? void 0 : o20 ? b7(s16, a20) : s16, h11 = r28.length - 1, l10; h11 >= 0; h11--)
    (l10 = r28[h11]) && (t20 = (o20 ? l10(s16, a20, t20) : l10(t20)) || t20);
  return o20 && t20 && v7(s16, a20, t20), t20;
};
var e15 = class extends o5 {
  constructor() {
    super(...arguments), this.variant = "text", this.width = "", this.height = "";
  }
  render() {
    const r28 = [
      this.width ? `width: ${this.width}` : "",
      this.height ? `height: ${this.height}` : ""
    ].filter(Boolean).join("; ");
    return b2`
      <div
        class="skeleton"
        part="skeleton"
        style=${r28}
        aria-busy="true"
        aria-label="Loading"
      ></div>
    `;
  }
};
e15.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }

      .skeleton {
        background: var(--bh-skeleton-color, var(--bh-color-secondary));
        animation: pulse 1.5s var(--bh-ease-in-out) infinite;
      }

      /* Text */
      :host([variant='text']) .skeleton,
      .skeleton {
        height: 1em;
        width: 100%;
        border-radius: var(--bh-radius-sm);
      }

      /* Circle */
      :host([variant='circle']) .skeleton {
        border-radius: var(--bh-radius-full);
      }

      /* Rect */
      :host([variant='rect']) .skeleton {
        border-radius: var(--bh-radius-md);
      }

      @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.4; }
      }
    `
];
i11([
  n5({ reflect: true })
], e15.prototype, "variant", 2);
i11([
  n5()
], e15.prototype, "width", 2);
i11([
  n5()
], e15.prototype, "height", 2);
e15 = i11([
  t3("bh-skeleton")
], e15);

// dist/atoms/spinner/bh-spinner.js
var v8 = Object.defineProperty;
var u7 = Object.getOwnPropertyDescriptor;
var n8 = (a20, r28, i20, s16) => {
  for (var e31 = s16 > 1 ? void 0 : s16 ? u7(r28, i20) : r28, o20 = a20.length - 1, l10; o20 >= 0; o20--)
    (l10 = a20[o20]) && (e31 = (s16 ? l10(r28, i20, e31) : l10(e31)) || e31);
  return s16 && e31 && v8(r28, i20, e31), e31;
};
var t12 = class extends o5 {
  constructor() {
    super(...arguments), this.size = "md", this.label = "Loading";
  }
  render() {
    return b2`
      <svg
        part="spinner"
        viewBox="0 0 24 24"
        fill="none"
        role="status"
        aria-label=${this.label || A}
      >
        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
        ></path>
      </svg>
    `;
  }
};
t12.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: inline-flex;
        align-items: center;
        justify-content: center;
      }

      svg {
        animation: spin 0.75s linear infinite;
        color: currentColor;
      }

      :host([size='sm']) svg {
        width: 1rem;
        height: 1rem;
      }

      svg,
      :host([size='md']) svg {
        width: 1.25rem;
        height: 1.25rem;
      }

      :host([size='lg']) svg {
        width: 1.5rem;
        height: 1.5rem;
      }

      circle {
        opacity: 0.25;
      }

      path {
        opacity: 0.75;
      }

      @keyframes spin {
        to {
          transform: rotate(360deg);
        }
      }
    `
];
n8([
  n5({ reflect: true })
], t12.prototype, "size", 2);
n8([
  n5()
], t12.prototype, "label", 2);
t12 = n8([
  t3("bh-spinner")
], t12);

// dist/atoms/switch/bh-switch.js
var v9 = Object.defineProperty;
var f6 = Object.getOwnPropertyDescriptor;
var h4 = (r28, t20, i20, s16) => {
  for (var e31 = s16 > 1 ? void 0 : s16 ? f6(t20, i20) : t20, l10 = r28.length - 1, o20; l10 >= 0; l10--)
    (o20 = r28[l10]) && (e31 = (s16 ? o20(t20, i20, e31) : o20(e31)) || e31);
  return s16 && e31 && v9(t20, i20, e31), e31;
};
var a7 = class extends o5 {
  constructor() {
    super(...arguments), this.checked = false, this.disabled = false, this.label = "";
  }
  render() {
    return b2`
      <label>
        <input
          type="checkbox"
          role="switch"
          .checked=${this.checked}
          ?disabled=${this.disabled}
          aria-checked=${this.checked ? "true" : "false"}
          aria-label=${this.label || A}
          @change=${this._handleChange}
        />
        <span class="track" part="track">
          <span class="thumb" part="thumb"></span>
        </span>
        <span class="label" part="label"><slot>${this.label}</slot></span>
      </label>
    `;
  }
  _handleChange(r28) {
    const t20 = r28.target;
    this.checked = t20.checked, this.dispatchEvent(
      new CustomEvent("bh-change", {
        bubbles: true,
        composed: true,
        detail: { checked: this.checked }
      })
    );
  }
};
a7.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: inline-flex;
        align-items: center;
        gap: var(--bh-spacing-2);
        cursor: pointer;
      }

      :host([disabled]) {
        opacity: 0.5;
        cursor: not-allowed;
      }

      input {
        position: absolute;
        width: 1px;
        height: 1px;
        padding: 0;
        margin: -1px;
        overflow: hidden;
        clip: rect(0, 0, 0, 0);
        white-space: nowrap;
        border-width: 0;
      }

      .track {
        position: relative;
        width: var(--bh-switch-width, 2.5rem);
        height: var(--bh-switch-height, 1.5rem);
        border-radius: var(--bh-radius-full);
        background: var(--bh-color-secondary);
        transition: all var(--bh-transition-fast);
        flex-shrink: 0;
      }

      .thumb {
        position: absolute;
        top: 2px;
        left: 2px;
        width: calc(var(--bh-switch-height, 1.5rem) - 4px);
        height: calc(var(--bh-switch-height, 1.5rem) - 4px);
        border-radius: var(--bh-radius-full);
        background: var(--bh-color-white);
        box-shadow: var(--bh-shadow-sm);
        transition: all var(--bh-transition-fast);
      }

      /* Checked */
      :host([checked]) .track {
        background: var(--bh-color-primary);
      }

      :host([checked]) .thumb {
        transform: translateX(calc(var(--bh-switch-width, 2.5rem) - var(--bh-switch-height, 1.5rem)));
      }

      /* Focus */
      input:focus-visible ~ .track {
        outline: 2px solid var(--bh-color-ring);
        outline-offset: 2px;
      }

      /* Label */
      .label {
        font-family: var(--bh-font-sans);
        font-size: var(--bh-text-base);
        line-height: var(--bh-leading-normal);
        color: var(--bh-color-text);
        user-select: none;
      }
    `
];
h4([
  n5({ type: Boolean, reflect: true })
], a7.prototype, "checked", 2);
h4([
  n5({ type: Boolean, reflect: true })
], a7.prototype, "disabled", 2);
h4([
  n5()
], a7.prototype, "label", 2);
a7 = h4([
  t3("bh-switch")
], a7);

// dist/atoms/text/bh-text.js
var g8 = Object.defineProperty;
var c6 = Object.getOwnPropertyDescriptor;
var l5 = (r28, e31, n14, o20) => {
  for (var t20 = o20 > 1 ? void 0 : o20 ? c6(e31, n14) : e31, i20 = r28.length - 1, s16; i20 >= 0; i20--)
    (s16 = r28[i20]) && (t20 = (o20 ? s16(e31, n14, t20) : s16(t20)) || t20);
  return o20 && t20 && g8(e31, n14, t20), t20;
};
var a8 = class extends o5 {
  constructor() {
    super(...arguments), this.variant = "body", this.truncate = false;
  }
  render() {
    const r28 = this.variant === "heading" ? "heading" : A, e31 = this.variant === "heading" ? "2" : A;
    return b2`
      <span
        part="text"
        role=${r28}
        aria-level=${e31}
      >
        <slot></slot>
      </span>
    `;
  }
};
a8.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
        color: var(--bh-color-text);
        font-family: var(--bh-font-sans);
      }

      /* Body (default) */
      :host,
      :host([variant='body']) {
        font-size: var(--bh-body-size);
        font-weight: var(--bh-body-weight);
        line-height: var(--bh-body-leading);
      }

      /* Heading */
      :host([variant='heading']) {
        font-size: var(--bh-heading-size);
        font-weight: var(--bh-heading-weight);
        line-height: var(--bh-heading-leading);
      }

      /* Small */
      :host([variant='small']) {
        font-size: var(--bh-small-size);
        font-weight: var(--bh-small-weight);
        line-height: var(--bh-small-leading);
        color: var(--bh-color-text-muted);
      }

      /* Code */
      :host([variant='code']) {
        font-family: var(--bh-font-mono);
        font-size: var(--bh-text-sm);
        line-height: var(--bh-leading-relaxed);
      }

      /* Truncation */
      :host([truncate]) {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      span {
        display: contents;
      }
    `
];
l5([
  n5({ reflect: true })
], a8.prototype, "variant", 2);
l5([
  n5({ type: Boolean, reflect: true })
], a8.prototype, "truncate", 2);
a8 = l5([
  t3("bh-text")
], a8);

// dist/atoms/textarea/bh-textarea.js
var f7 = Object.defineProperty;
var x2 = Object.getOwnPropertyDescriptor;
var r12 = (s16, a20, h11, i20) => {
  for (var o20 = i20 > 1 ? void 0 : i20 ? x2(a20, h11) : a20, n14 = s16.length - 1, p9; n14 >= 0; n14--)
    (p9 = s16[n14]) && (o20 = (i20 ? p9(a20, h11, o20) : p9(o20)) || o20);
  return i20 && o20 && f7(a20, h11, o20), o20;
};
var e16 = class extends o5 {
  constructor() {
    super(...arguments), this.size = "md", this.value = "", this.placeholder = "", this.name = "", this.label = "", this.rows = 3, this.resize = "vertical", this.disabled = false, this.readonly = false, this.required = false, this.error = false;
  }
  render() {
    return b2`
      <div class="wrapper" part="wrapper">
        <textarea
          part="textarea"
          .value=${l4(this.value)}
          placeholder=${this.placeholder || A}
          name=${this.name || A}
          aria-label=${this.label || A}
          rows=${this.rows}
          ?disabled=${this.disabled}
          ?readonly=${this.readonly}
          ?required=${this.required}
          aria-invalid=${this.error ? "true" : A}
          @input=${this._handleInput}
          @change=${this._handleChange}
        ></textarea>
      </div>
    `;
  }
  _handleInput(s16) {
    const a20 = s16.target;
    this.value = a20.value, this.dispatchEvent(
      new CustomEvent("bh-input", {
        bubbles: true,
        composed: true,
        detail: { value: this.value }
      })
    );
  }
  _handleChange(s16) {
    const a20 = s16.target;
    this.value = a20.value, this.dispatchEvent(
      new CustomEvent("bh-change", {
        bubbles: true,
        composed: true,
        detail: { value: this.value }
      })
    );
  }
};
e16.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }

      .wrapper {
        display: flex;
        width: 100%;
        background: var(--bh-textarea-bg, var(--bh-color-surface-raised));
        border: var(--bh-border-1) solid var(--bh-textarea-border, var(--bh-color-border));
        border-radius: var(--bh-textarea-radius, var(--bh-radius-md));
        box-shadow: var(--bh-shadow-inset);
        transition: all var(--bh-transition-fast);
      }

      textarea {
        flex: 1;
        min-width: 0;
        font-family: var(--bh-font-sans);
        line-height: var(--bh-leading-normal);
        color: var(--bh-textarea-color, var(--bh-color-text));
        background: transparent;
        border: none;
        outline: none;
        resize: vertical;
      }

      textarea::placeholder {
        color: var(--bh-color-text-muted);
      }

      /* Resize */
      :host([resize='none']) textarea { resize: none; }
      :host([resize='vertical']) textarea { resize: vertical; }
      :host([resize='horizontal']) textarea { resize: horizontal; }
      :host([resize='both']) textarea { resize: both; }

      /* Sizes */
      :host([size='sm']) .wrapper {
        font-size: var(--bh-text-sm);
        padding: var(--bh-spacing-1-5) var(--bh-spacing-3);
      }

      .wrapper,
      :host([size='md']) .wrapper {
        font-size: var(--bh-text-base);
        padding: var(--bh-spacing-2) var(--bh-spacing-4);
      }

      :host([size='lg']) .wrapper {
        font-size: var(--bh-text-lg);
        padding: var(--bh-spacing-2-5) var(--bh-spacing-6);
      }

      textarea {
        font-size: inherit;
      }

      /* Focus */
      .wrapper:focus-within {
        border-color: var(--bh-color-ring);
        box-shadow: 0 0 0 1px var(--bh-color-ring);
      }

      /* Error */
      :host([error]) .wrapper {
        border-color: var(--bh-color-danger);
      }

      :host([error]) .wrapper:focus-within {
        border-color: var(--bh-color-danger);
        box-shadow: 0 0 0 1px var(--bh-color-danger);
      }

      /* Disabled */
      :host([disabled]) .wrapper {
        opacity: 0.5;
        cursor: not-allowed;
      }

      :host([disabled]) textarea {
        cursor: not-allowed;
      }

      /* Readonly */
      :host([readonly]) .wrapper {
        background: var(--bh-color-surface);
      }
    `
];
r12([
  n5({ reflect: true })
], e16.prototype, "size", 2);
r12([
  n5()
], e16.prototype, "value", 2);
r12([
  n5()
], e16.prototype, "placeholder", 2);
r12([
  n5()
], e16.prototype, "name", 2);
r12([
  n5()
], e16.prototype, "label", 2);
r12([
  n5({ type: Number })
], e16.prototype, "rows", 2);
r12([
  n5({ reflect: true })
], e16.prototype, "resize", 2);
r12([
  n5({ type: Boolean, reflect: true })
], e16.prototype, "disabled", 2);
r12([
  n5({ type: Boolean, reflect: true })
], e16.prototype, "readonly", 2);
r12([
  n5({ type: Boolean, reflect: true })
], e16.prototype, "required", 2);
r12([
  n5({ type: Boolean, reflect: true })
], e16.prototype, "error", 2);
e16 = r12([
  t3("bh-textarea")
], e16);

// dist/atoms/tooltip/bh-tooltip.js
var b8 = Object.defineProperty;
var v10 = Object.getOwnPropertyDescriptor;
var i12 = (p9, r28, a20, e31) => {
  for (var t20 = e31 > 1 ? void 0 : e31 ? v10(r28, a20) : r28, n14 = p9.length - 1, s16; n14 >= 0; n14--)
    (s16 = p9[n14]) && (t20 = (e31 ? s16(r28, a20, t20) : s16(t20)) || t20);
  return e31 && t20 && b8(r28, a20, t20), t20;
};
var o10 = class extends o5 {
  constructor() {
    super(...arguments), this.content = "", this.placement = "top";
  }
  render() {
    return b2`
      <span class="trigger">
        <slot></slot>
      </span>
      <span class="tooltip" part="tooltip" role="tooltip">${this.content}</span>
    `;
  }
};
o10.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: inline-flex;
        position: relative;
      }

      .trigger {
        display: inline-flex;
      }

      .tooltip {
        position: absolute;
        z-index: var(--bh-z-tooltip);
        padding: var(--bh-spacing-1-5) var(--bh-spacing-3);
        font-family: var(--bh-font-sans);
        font-size: var(--bh-text-sm);
        line-height: var(--bh-leading-normal);
        white-space: nowrap;
        border-radius: var(--bh-radius-md);
        background: var(--bh-tooltip-bg, var(--bh-color-cod));
        color: var(--bh-tooltip-color, var(--bh-color-white));
        pointer-events: none;
        opacity: 0;
        transition: opacity var(--bh-transition-fast);
      }

      :host(:hover) .tooltip,
      :host(:focus-within) .tooltip {
        opacity: 1;
      }

      /* Placements */
      :host([placement='top']) .tooltip,
      .tooltip {
        bottom: 100%;
        left: 50%;
        transform: translateX(-50%);
        margin-bottom: var(--bh-spacing-1-5);
      }

      :host([placement='bottom']) .tooltip {
        top: 100%;
        left: 50%;
        transform: translateX(-50%);
        margin-top: var(--bh-spacing-1-5);
      }

      :host([placement='left']) .tooltip {
        right: 100%;
        top: 50%;
        transform: translateY(-50%);
        margin-right: var(--bh-spacing-1-5);
      }

      :host([placement='right']) .tooltip {
        left: 100%;
        top: 50%;
        transform: translateY(-50%);
        margin-left: var(--bh-spacing-1-5);
      }
    `
];
i12([
  n5()
], o10.prototype, "content", 2);
i12([
  n5({ reflect: true })
], o10.prototype, "placement", 2);
o10 = i12([
  t3("bh-tooltip")
], o10);

// dist/atoms/pixel-display/bh-pixel-display.js
var u8 = Object.defineProperty;
var w2 = Object.getOwnPropertyDescriptor;
var p5 = (s16, e31, t20, l10) => {
  for (var r28 = l10 > 1 ? void 0 : l10 ? w2(e31, t20) : e31, a20 = s16.length - 1, i20; a20 >= 0; a20--)
    (i20 = s16[a20]) && (r28 = (l10 ? i20(e31, t20, r28) : i20(r28)) || r28);
  return l10 && r28 && u8(e31, t20, r28), r28;
};
var d7 = ["off", "primary", "success", "warning", "danger"];
var o11 = class extends o5 {
  constructor() {
    super(...arguments), this.cols = 20, this.rows = 5, this.label = "", this._pixelEls = [];
  }
  render() {
    const s16 = this.cols * this.rows, e31 = this.label.length > 0;
    return b2`
      <div
        class="grid"
        part="grid"
        role=${e31 ? "img" : A}
        aria-label=${e31 ? this.label : A}
        aria-hidden=${e31 ? A : "true"}
        style="--_cols:${this.cols};--_rows:${this.rows}"
      >
        ${Array.from(
      { length: s16 },
      () => b2`<div class="px" part="pixel" aria-hidden="true"></div>`
    )}
      </div>
    `;
  }
  updated() {
    const s16 = this.data, e31 = this._prevData, t20 = this.shadowRoot.querySelector(".grid");
    if (!t20) return;
    this._pixelEls = Array.from(t20.querySelectorAll(".px"));
    const l10 = this.cols * this.rows;
    for (let r28 = 0; r28 < l10 && r28 < this._pixelEls.length; r28++) {
      const a20 = s16 && r28 < s16.length ? s16[r28] : 0, i20 = e31 && r28 < e31.length ? e31[r28] : -1;
      if (a20 !== i20) {
        const x4 = this._pixelEls[r28];
        x4.className = `px ${a20 > 0 && a20 < d7.length ? d7[a20] : ""}`.trimEnd();
      }
    }
    s16 && (this._prevData = new Uint8Array(s16));
  }
};
o11.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: inline-block;
      }

      .grid {
        display: grid;
        grid-template-columns: repeat(var(--_cols), var(--bh-pixel-size, 4px));
        grid-template-rows: repeat(var(--_rows), var(--bh-pixel-size, 4px));
        gap: var(--bh-pixel-gap, 1px);
      }

      .px {
        width: var(--bh-pixel-size, 4px);
        height: var(--bh-pixel-size, 4px);
        border-radius: var(--bh-pixel-radius, 1px);
        background: var(--bh-pixel-off, var(--bh-color-surface-recessed));
        transition: background 0.15s, box-shadow 0.15s;
      }

      .px.primary {
        background: var(--bh-color-primary);
        box-shadow: 0 0 var(--bh-pixel-glow, 4px) var(--bh-color-primary-glow);
      }

      .px.success {
        background: var(--bh-color-success);
        box-shadow: 0 0 var(--bh-pixel-glow, 4px) var(--bh-color-success-dim);
      }

      .px.warning {
        background: var(--bh-color-warning);
        box-shadow: 0 0 var(--bh-pixel-glow, 4px) var(--bh-color-warning-dim);
      }

      .px.danger {
        background: var(--bh-color-danger);
        box-shadow: 0 0 var(--bh-pixel-glow, 4px) rgba(239, 68, 68, 0.4);
      }
    `
];
p5([
  n5({ type: Number })
], o11.prototype, "cols", 2);
p5([
  n5({ type: Number })
], o11.prototype, "rows", 2);
p5([
  n5({ attribute: false })
], o11.prototype, "data", 2);
p5([
  n5()
], o11.prototype, "label", 2);
o11 = p5([
  t3("bh-pixel-display")
], o11);

// dist/atoms/segment-display/bh-segment-display.js
var y3 = Object.defineProperty;
var d8 = Object.getOwnPropertyDescriptor;
var o12 = (e31, a20, n14, l10) => {
  for (var t20 = l10 > 1 ? void 0 : l10 ? d8(a20, n14) : a20, h11 = e31.length - 1, i20; h11 >= 0; h11--)
    (i20 = e31[h11]) && (t20 = (l10 ? i20(a20, n14, t20) : i20(t20)) || t20);
  return l10 && t20 && y3(a20, n14, t20), t20;
};
var s7 = class extends o5 {
  constructor() {
    super(...arguments), this.value = "", this.color = "primary", this.size = "md", this.ghost = false, this.label = "";
  }
  /** Character used for ghost segments. Defaults to '8' for digits, '~' for alpha. */
  get _ghostText() {
    return this.value.toUpperCase().split("").map((e31) => /[0-9]/.test(e31) ? "8" : /[A-Z]/.test(e31) ? "~" : e31).join("");
  }
  render() {
    const e31 = this.value.toUpperCase();
    return this.ghost ? b2`
        <span class="wrapper">
          <span
            class="display ghost"
            aria-hidden="true"
          >${this._ghostText}</span>
          <span
            class="display"
            part="display"
            role="status"
            aria-label=${this.label || A}
          >${e31}</span>
        </span>
      ` : b2`
      <span
        class="display"
        part="display"
        role="status"
        aria-label=${this.label || A}
      >${e31}</span>
    `;
  }
};
s7.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: inline-block;
        font-family: 'DSEG14Classic', 'DSEG14', var(--bh-font-mono);
        text-transform: uppercase;
      }

      .display {
        font-size: var(--bh-segment-size, 14px);
        font-weight: normal;
        letter-spacing: var(--bh-segment-tracking, 1px);
        color: var(--bh-segment-color);
        text-shadow: 0 0 8px var(--bh-segment-glow);
        line-height: var(--bh-leading-none);
      }

      /* Ghost segments behind the lit text */
      :host([ghost]) .ghost {
        position: absolute;
        inset: 0;
        color: var(--bh-segment-off, var(--bh-color-surface-recessed));
        text-shadow: none;
        pointer-events: none;
        user-select: none;
      }

      :host([ghost]) .wrapper {
        position: relative;
        display: inline-block;
      }

      /* Sizes */
      :host([size='sm']) .display,
      :host([size='sm']) .ghost {
        --bh-segment-size: 10px;
        --bh-segment-tracking: 0.5px;
      }

      .display,
      .ghost,
      :host([size='md']) .display,
      :host([size='md']) .ghost {
        --bh-segment-size: 14px;
        --bh-segment-tracking: 1px;
      }

      :host([size='lg']) .display,
      :host([size='lg']) .ghost {
        --bh-segment-size: 20px;
        --bh-segment-tracking: 1.5px;
      }

      :host([size='xl']) .display,
      :host([size='xl']) .ghost {
        --bh-segment-size: 28px;
        --bh-segment-tracking: 2px;
      }

      /* Colors */
      :host,
      :host([color='primary']) {
        --bh-segment-color: var(--bh-color-primary);
        --bh-segment-glow: var(--bh-color-primary-glow, rgba(255, 107, 53, 0.25));
      }

      :host([color='success']) {
        --bh-segment-color: var(--bh-color-success);
        --bh-segment-glow: var(--bh-color-success-dim, rgba(42, 157, 78, 0.25));
      }

      :host([color='warning']) {
        --bh-segment-color: var(--bh-color-warning);
        --bh-segment-glow: rgba(245, 158, 11, 0.25);
      }

      :host([color='danger']) {
        --bh-segment-color: var(--bh-color-danger);
        --bh-segment-glow: rgba(220, 38, 38, 0.25);
      }

      :host([color='default']) {
        --bh-segment-color: var(--bh-color-text);
        --bh-segment-glow: transparent;
      }
    `
];
o12([
  n5()
], s7.prototype, "value", 2);
o12([
  n5({ reflect: true })
], s7.prototype, "color", 2);
o12([
  n5({ reflect: true })
], s7.prototype, "size", 2);
o12([
  n5({ type: Boolean, reflect: true })
], s7.prototype, "ghost", 2);
o12([
  n5()
], s7.prototype, "label", 2);
s7 = o12([
  t3("bh-segment-display")
], s7);

// dist/atoms/slider/bh-slider.js
var v11 = Object.defineProperty;
var m5 = Object.getOwnPropertyDescriptor;
var r13 = (s16, t20, n14, o20) => {
  for (var a20 = o20 > 1 ? void 0 : o20 ? m5(t20, n14) : t20, l10 = s16.length - 1, h11; l10 >= 0; l10--)
    (h11 = s16[l10]) && (a20 = (o20 ? h11(t20, n14, a20) : h11(a20)) || a20);
  return o20 && a20 && v11(t20, n14, a20), a20;
};
var e17 = class extends o5 {
  constructor() {
    super(...arguments), this.min = 0, this.max = 100, this.step = 1, this.value = 0, this.disabled = false, this.showValue = false, this.label = "";
  }
  render() {
    return b2`
      <div class="slider">
        <input
          part="track"
          type="range"
          .min=${String(this.min)}
          .max=${String(this.max)}
          .step=${String(this.step)}
          .value=${String(this.value)}
          ?disabled=${this.disabled}
          aria-label=${this.label || "Slider"}
          @input=${this._handleInput}
          @change=${this._handleChange}
        />
        ${this.showValue ? b2`<span class="value" part="value">${this.value}</span>` : ""}
      </div>
    `;
  }
  _handleInput(s16) {
    const t20 = s16.target;
    this.value = Number(t20.value), this.dispatchEvent(
      new CustomEvent("bh-input", {
        bubbles: true,
        composed: true,
        detail: { value: this.value }
      })
    );
  }
  _handleChange(s16) {
    const t20 = s16.target;
    this.value = Number(t20.value), this.dispatchEvent(
      new CustomEvent("bh-change", {
        bubbles: true,
        composed: true,
        detail: { value: this.value }
      })
    );
  }
};
e17.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }

      .slider {
        display: flex;
        align-items: center;
        gap: var(--bh-spacing-3);
      }

      input[type='range'] {
        -webkit-appearance: none;
        appearance: none;
        flex: 1;
        height: var(--bh-slider-track-height, 4px);
        background: var(--bh-slider-track-color, var(--bh-color-surface-raised));
        border-radius: var(--bh-radius-full);
        outline: none;
        margin: 0;
      }

      input[type='range']::-webkit-slider-thumb {
        -webkit-appearance: none;
        appearance: none;
        width: var(--bh-slider-thumb-size, 14px);
        height: var(--bh-slider-thumb-size, 14px);
        border-radius: 50%;
        background: var(--bh-slider-thumb-color, var(--bh-color-primary));
        cursor: pointer;
        transition: box-shadow var(--bh-transition-fast);
      }

      input[type='range']:focus-visible::-webkit-slider-thumb {
        box-shadow: 0 0 0 var(--bh-border-2) var(--bh-color-ring);
      }

      input[type='range']::-moz-range-thumb {
        width: var(--bh-slider-thumb-size, 14px);
        height: var(--bh-slider-thumb-size, 14px);
        border: none;
        border-radius: 50%;
        background: var(--bh-slider-thumb-color, var(--bh-color-primary));
        cursor: pointer;
      }

      input[type='range']:focus-visible::-moz-range-thumb {
        box-shadow: 0 0 0 var(--bh-border-2) var(--bh-color-ring);
      }

      .value {
        font-family: var(--bh-font-mono);
        font-size: var(--bh-text-sm);
        color: var(--bh-color-text-muted);
        font-variant-numeric: tabular-nums;
        min-width: 2ch;
        text-align: end;
      }

      /* Disabled */
      :host([disabled]) {
        opacity: 0.5;
        pointer-events: none;
      }
    `
];
r13([
  n5({ type: Number })
], e17.prototype, "min", 2);
r13([
  n5({ type: Number })
], e17.prototype, "max", 2);
r13([
  n5({ type: Number })
], e17.prototype, "step", 2);
r13([
  n5({ type: Number })
], e17.prototype, "value", 2);
r13([
  n5({ type: Boolean, reflect: true })
], e17.prototype, "disabled", 2);
r13([
  n5({ type: Boolean, reflect: true, attribute: "show-value" })
], e17.prototype, "showValue", 2);
r13([
  n5()
], e17.prototype, "label", 2);
e17 = r13([
  t3("bh-slider")
], e17);

// dist/atoms/terminal-cursor/bh-terminal-cursor.js
var b9 = Object.defineProperty;
var f8 = Object.getOwnPropertyDescriptor;
var n9 = (p9, t20, o20, s16) => {
  for (var r28 = s16 > 1 ? void 0 : s16 ? f8(t20, o20) : t20, i20 = p9.length - 1, a20; i20 >= 0; i20--)
    (a20 = p9[i20]) && (r28 = (s16 ? a20(t20, o20, r28) : a20(r28)) || r28);
  return s16 && r28 && b9(t20, o20, r28), r28;
};
var e18 = class extends o5 {
  constructor() {
    super(...arguments), this.shape = "line", this.blink = true;
  }
  render() {
    return b2`<span part="cursor"></span>`;
  }
};
e18.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: inline-block;
      }

      span {
        display: inline-block;
        background: var(--bh-cursor-color, var(--bh-color-primary));
      }

      /* Shapes */
      span,
      :host([shape='line']) span {
        width: 2px;
        height: var(--bh-cursor-height, 1.2em);
      }

      :host([shape='block']) span {
        width: var(--bh-cursor-width, 8px);
        height: var(--bh-cursor-height, 1.2em);
      }

      :host([shape='underline']) span {
        width: var(--bh-cursor-width, 8px);
        height: 2px;
        vertical-align: bottom;
      }

      /* Blink animation */
      :host([blink]) span {
        animation: cursor-blink 1s ease-in-out infinite;
      }

      @keyframes cursor-blink {
        0%, 100% {
          opacity: 1;
        }
        50% {
          opacity: 0.2;
        }
      }
    `
];
n9([
  n5({ reflect: true })
], e18.prototype, "shape", 2);
n9([
  n5({ type: Boolean, reflect: true })
], e18.prototype, "blink", 2);
e18 = n9([
  t3("bh-terminal-cursor")
], e18);

// dist/molecules/card/bh-card.js
var v12 = Object.defineProperty;
var f9 = Object.getOwnPropertyDescriptor;
var t13 = (a20, r28, n14, s16) => {
  for (var o20 = s16 > 1 ? void 0 : s16 ? f9(r28, n14) : r28, h11 = a20.length - 1, i20; h11 >= 0; h11--)
    (i20 = a20[h11]) && (o20 = (s16 ? i20(r28, n14, o20) : i20(o20)) || o20);
  return s16 && o20 && v12(r28, n14, o20), o20;
};
var e19 = class extends o5 {
  constructor() {
    super(...arguments), this.variant = "default", this.padding = "md", this.cornerAccents = false, this._hasHeader = false, this._hasHeaderActions = false, this._hasFooter = false;
  }
  get _showHeader() {
    return this._hasHeader || this._hasHeaderActions;
  }
  render() {
    return b2`
      <div class="card" part="card">
        ${this._showHeader ? b2`<div class="header" part="header">
              <div class="header-start"><slot name="header" @slotchange=${this._onHeaderSlotChange}></slot></div>
              <div class="header-end"><slot name="header-actions" @slotchange=${this._onHeaderActionsSlotChange}></slot></div>
            </div>` : b2`<slot name="header" @slotchange=${this._onHeaderSlotChange}></slot>
                 <slot name="header-actions" @slotchange=${this._onHeaderActionsSlotChange}></slot>`}
        <div class="body" part="body">
          <slot></slot>
        </div>
        ${this._hasFooter ? b2`<div class="footer" part="footer"><slot name="footer" @slotchange=${this._onFooterSlotChange}></slot></div>` : b2`<slot name="footer" @slotchange=${this._onFooterSlotChange}></slot>`}
      </div>
    `;
  }
  _onHeaderSlotChange(a20) {
    const r28 = a20.target;
    this._hasHeader = r28.assignedNodes({ flatten: true }).length > 0;
  }
  _onHeaderActionsSlotChange(a20) {
    const r28 = a20.target;
    this._hasHeaderActions = r28.assignedNodes({ flatten: true }).length > 0;
  }
  _onFooterSlotChange(a20) {
    const r28 = a20.target;
    this._hasFooter = r28.assignedNodes({ flatten: true }).length > 0;
  }
};
e19.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }

      .card {
        position: relative;
        background: var(--bh-card-bg, var(--bh-color-surface-raised));
        border-radius: var(--bh-card-radius, var(--bh-radius-lg));
        overflow: hidden;
      }

      /* Corner accents */
      :host([corner-accents]) .card::before,
      :host([corner-accents]) .card::after {
        content: '';
        position: absolute;
        width: 12px;
        height: 12px;
        border-color: var(--bh-card-accent-color, var(--bh-color-border));
        border-style: solid;
        border-width: 0;
        transition: border-color 0.2s, box-shadow 0.2s;
        pointer-events: none;
        z-index: 1;
      }

      :host([corner-accents]) .card::before {
        top: 0;
        left: 0;
        border-top-width: 2px;
        border-left-width: 2px;
        border-top-left-radius: var(--bh-card-radius, var(--bh-radius-lg));
      }

      :host([corner-accents]) .card::after {
        bottom: 0;
        right: 0;
        border-bottom-width: 2px;
        border-right-width: 2px;
        border-bottom-right-radius: var(--bh-card-radius, var(--bh-radius-lg));
      }

      :host([corner-accents]) .card:hover::before,
      :host([corner-accents]) .card:hover::after {
        border-color: var(--bh-card-accent-hover-color, var(--bh-color-primary));
        box-shadow: 0 0 6px var(--bh-card-accent-glow, var(--bh-color-primary-glow));
      }

      /* Default — shadow, no border */
      .card,
      :host([variant='default']) .card {
        box-shadow: var(--bh-card-shadow, var(--bh-shadow-md));
        border: var(--bh-border-1) solid transparent;
      }

      /* Outlined — border, no shadow */
      :host([variant='outlined']) .card {
        border: var(--bh-border-1) solid var(--bh-card-border, var(--bh-color-border));
        box-shadow: none;
      }

      /* Flat — no border, no shadow */
      :host([variant='flat']) .card {
        border: var(--bh-border-1) solid transparent;
        box-shadow: none;
      }

      /* Padding */
      .body {
        padding: var(--bh-spacing-4);
      }

      :host([padding='none']) .body {
        padding: 0;
      }

      :host([padding='sm']) .body {
        padding: var(--bh-spacing-2);
      }

      :host([padding='md']) .body {
        padding: var(--bh-spacing-4);
      }

      :host([padding='lg']) .body {
        padding: var(--bh-spacing-6);
      }

      /* Header */
      .header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: var(--bh-spacing-2);
        padding: var(--bh-spacing-4);
        border-bottom: var(--bh-border-1) solid var(--bh-color-border);
      }

      :host([padding='sm']) .header {
        padding: var(--bh-spacing-2);
      }

      :host([padding='lg']) .header {
        padding: var(--bh-spacing-6);
      }

      :host([padding='none']) .header {
        padding: var(--bh-spacing-4);
      }

      .header-start {
        display: flex;
        align-items: center;
        gap: var(--bh-spacing-2);
        min-width: 0;
      }

      .header-end {
        display: flex;
        align-items: center;
        gap: var(--bh-spacing-2);
        flex-shrink: 0;
      }

      /* Footer */
      .footer {
        padding: var(--bh-spacing-4);
        border-top: var(--bh-border-1) solid var(--bh-color-border);
      }

      :host([padding='sm']) .footer {
        padding: var(--bh-spacing-2);
      }

      :host([padding='lg']) .footer {
        padding: var(--bh-spacing-6);
      }

      :host([padding='none']) .footer {
        padding: var(--bh-spacing-4);
      }
    `
];
t13([
  n5({ reflect: true })
], e19.prototype, "variant", 2);
t13([
  n5({ reflect: true })
], e19.prototype, "padding", 2);
t13([
  n5({ type: Boolean, reflect: true, attribute: "corner-accents" })
], e19.prototype, "cornerAccents", 2);
t13([
  r5()
], e19.prototype, "_hasHeader", 2);
t13([
  r5()
], e19.prototype, "_hasHeaderActions", 2);
t13([
  r5()
], e19.prototype, "_hasFooter", 2);
e19 = t13([
  t3("bh-card")
], e19);

// dist/molecules/chip/bh-chip.js
var v13 = Object.defineProperty;
var m6 = Object.getOwnPropertyDescriptor;
var o13 = (t20, s16, n14, a20) => {
  for (var e31 = a20 > 1 ? void 0 : a20 ? m6(s16, n14) : s16, h11 = t20.length - 1, l10; h11 >= 0; h11--)
    (l10 = t20[h11]) && (e31 = (a20 ? l10(s16, n14, e31) : l10(e31)) || e31);
  return a20 && e31 && v13(s16, n14, e31), e31;
};
var r14 = class extends o5 {
  constructor() {
    super(...arguments), this.variant = "default", this.size = "md", this.dismissible = false, this.selected = false, this.disabled = false;
  }
  render() {
    return b2`
      <button
        part="chip"
        ?disabled=${this.disabled}
        aria-pressed=${this.selected ? "true" : A}
        @click=${this._handleClick}
      >
        <slot name="prefix"></slot>
        <slot></slot>
        ${this.dismissible ? b2`<button
              class="dismiss"
              part="dismiss"
              aria-label="Remove"
              tabindex="-1"
              @click=${this._handleDismiss}
            ><bh-icon name="x"></bh-icon></button>` : A}
      </button>
    `;
  }
  _handleClick(t20) {
    if (this.disabled) {
      t20.preventDefault(), t20.stopPropagation();
      return;
    }
    this.dispatchEvent(
      new CustomEvent("bh-click", {
        bubbles: true,
        composed: true,
        detail: { originalEvent: t20 }
      })
    );
  }
  _handleDismiss(t20) {
    t20.stopPropagation(), !this.disabled && this.dispatchEvent(
      new CustomEvent("bh-dismiss", {
        bubbles: true,
        composed: true,
        detail: {}
      })
    );
  }
};
r14.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: inline-block;
      }

      button {
        display: inline-flex;
        align-items: center;
        gap: var(--bh-spacing-1-5);
        border: var(--bh-border-1) solid transparent;
        cursor: pointer;
        font-family: var(--bh-font-sans);
        font-weight: var(--bh-font-medium);
        line-height: var(--bh-leading-none);
        border-radius: var(--bh-chip-radius, var(--bh-radius-full));
        background: var(--bh-chip-bg);
        color: var(--bh-chip-color);
        transition: all var(--bh-transition-fast);
      }

      /* Sizes */
      :host([size='sm']) button {
        font-size: var(--bh-text-xs);
        padding: var(--bh-spacing-0-5) var(--bh-spacing-2);
      }

      button,
      :host([size='md']) button {
        font-size: var(--bh-text-sm);
        padding: var(--bh-spacing-1) var(--bh-spacing-2-5);
      }

      /* Default */
      button,
      :host([variant='default']) button {
        --bh-chip-bg: var(--bh-color-secondary);
        --bh-chip-color: var(--bh-color-secondary-text);
      }

      :host([variant='default']) button:hover,
      button:hover {
        --bh-chip-bg: var(--bh-color-secondary-hover);
      }

      /* Primary */
      :host([variant='primary']) button {
        --bh-chip-bg: var(--bh-color-primary);
        --bh-chip-color: var(--bh-color-primary-text);
      }

      :host([variant='primary']) button:hover {
        --bh-chip-bg: var(--bh-color-primary-hover);
      }

      /* Success */
      :host([variant='success']) button {
        --bh-chip-bg: var(--bh-color-success);
        --bh-chip-color: var(--bh-color-text-inverse);
      }

      :host([variant='success']) button:hover {
        --bh-chip-bg: var(--bh-color-success-hover);
      }

      /* Warning */
      :host([variant='warning']) button {
        --bh-chip-bg: var(--bh-color-warning);
        --bh-chip-color: var(--bh-color-text);
      }

      :host([variant='warning']) button:hover {
        --bh-chip-bg: var(--bh-color-warning-hover);
      }

      /* Danger */
      :host([variant='danger']) button {
        --bh-chip-bg: var(--bh-color-danger);
        --bh-chip-color: var(--bh-color-danger-text);
      }

      :host([variant='danger']) button:hover {
        --bh-chip-bg: var(--bh-color-danger-hover);
      }

      /* Selected */
      :host([selected]) button {
        border-color: currentColor;
        box-shadow: 0 0 0 1px currentColor;
      }

      /* Focus */
      button:focus-visible {
        outline: 2px solid var(--bh-color-ring);
        outline-offset: 2px;
      }

      /* Disabled */
      :host([disabled]) button {
        opacity: 0.5;
        cursor: not-allowed;
        pointer-events: none;
      }

      /* Dismiss */
      .dismiss {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 0;
        margin: 0;
        margin-left: var(--bh-spacing-0-5);
        border: none;
        background: none;
        color: inherit;
        cursor: pointer;
        border-radius: var(--bh-radius-full);
        width: 1em;
        height: 1em;
        line-height: 1;
        opacity: 0.7;
        transition: opacity var(--bh-transition-fast);
      }

      .dismiss:hover {
        opacity: 1;
      }

      .dismiss:focus-visible {
        outline: 2px solid var(--bh-color-ring);
        outline-offset: 1px;
      }

      .dismiss bh-icon {
        --bh-icon-size: 1em;
        color: inherit;
      }
    `
];
o13([
  n5({ reflect: true })
], r14.prototype, "variant", 2);
o13([
  n5({ reflect: true })
], r14.prototype, "size", 2);
o13([
  n5({ type: Boolean, reflect: true })
], r14.prototype, "dismissible", 2);
o13([
  n5({ type: Boolean, reflect: true })
], r14.prototype, "selected", 2);
o13([
  n5({ type: Boolean, reflect: true })
], r14.prototype, "disabled", 2);
r14 = o13([
  t3("bh-chip")
], r14);

// dist/molecules/form-field/bh-form-field.js
var m7 = Object.defineProperty;
var v14 = Object.getOwnPropertyDescriptor;
var a9 = (i20, e31, l10, o20) => {
  for (var r28 = o20 > 1 ? void 0 : o20 ? v14(e31, l10) : e31, d19 = i20.length - 1, b20; d19 >= 0; d19--)
    (b20 = i20[d19]) && (r28 = (o20 ? b20(e31, l10, r28) : b20(r28)) || r28);
  return o20 && r28 && m7(e31, l10, r28), r28;
};
var g9 = 0;
var t14 = class extends o5 {
  constructor() {
    super(...arguments), this.label = "", this.helpText = "", this.error = "", this.required = false, this._uniqueId = `bh-ff-${++g9}`;
  }
  render() {
    const i20 = `${this._uniqueId}-label`, e31 = `${this._uniqueId}-help`, l10 = `${this._uniqueId}-error`;
    return b2`
      <div class="field" part="field">
        ${this.label ? b2`<label id=${i20} part="label">
              ${this.label}${this.required ? b2`<span class="required-marker" aria-hidden="true">*</span>` : A}
            </label>` : A}
        <slot @slotchange=${this._onSlotChange}></slot>
        ${this.helpText && !this.error ? b2`<div id=${e31} class="help-text" part="help-text">${this.helpText}</div>` : A}
        ${this.error ? b2`<div id=${l10} class="error" part="error" role="alert">${this.error}</div>` : A}
      </div>
    `;
  }
  updated() {
    this._linkAria();
  }
  _onSlotChange() {
    this._linkAria();
  }
  _linkAria() {
    if (!this._defaultSlot) return;
    const i20 = this._defaultSlot.assignedElements({ flatten: true });
    if (i20.length === 0) return;
    const e31 = i20[0], l10 = `${this._uniqueId}-label`, o20 = `${this._uniqueId}-help`, r28 = `${this._uniqueId}-error`;
    this.label ? e31.setAttribute("aria-labelledby", l10) : e31.removeAttribute("aria-labelledby"), this.error ? e31.setAttribute("aria-describedby", r28) : this.helpText ? e31.setAttribute("aria-describedby", o20) : e31.removeAttribute("aria-describedby"), this.error ? e31.setAttribute("aria-invalid", "true") : e31.removeAttribute("aria-invalid"), this.required ? e31.setAttribute("aria-required", "true") : e31.removeAttribute("aria-required");
  }
};
t14.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }

      .field {
        display: flex;
        flex-direction: column;
        gap: var(--bh-form-field-gap, var(--bh-spacing-1-5));
      }

      label {
        font-family: var(--bh-font-sans);
        font-size: var(--bh-text-sm);
        font-weight: var(--bh-font-medium);
        line-height: var(--bh-leading-normal);
        color: var(--bh-form-field-label-color, var(--bh-color-text));
      }

      .required-marker {
        color: var(--bh-form-field-error-color, var(--bh-color-danger));
        margin-left: var(--bh-spacing-0-5);
      }

      .help-text {
        font-family: var(--bh-font-sans);
        font-size: var(--bh-text-sm);
        line-height: var(--bh-leading-normal);
        color: var(--bh-color-text-muted);
      }

      .error {
        font-family: var(--bh-font-sans);
        font-size: var(--bh-text-sm);
        line-height: var(--bh-leading-normal);
        color: var(--bh-form-field-error-color, var(--bh-color-danger));
      }
    `
];
a9([
  n5()
], t14.prototype, "label", 2);
a9([
  n5({ attribute: "help-text" })
], t14.prototype, "helpText", 2);
a9([
  n5()
], t14.prototype, "error", 2);
a9([
  n5({ type: Boolean })
], t14.prototype, "required", 2);
a9([
  e6("slot:not([name])")
], t14.prototype, "_defaultSlot", 2);
t14 = a9([
  t3("bh-form-field")
], t14);

// dist/molecules/nav-item/bh-nav-item.js
var d9 = Object.defineProperty;
var u9 = Object.getOwnPropertyDescriptor;
var r15 = (a20, o20, l10, s16) => {
  for (var t20 = s16 > 1 ? void 0 : s16 ? u9(o20, l10) : o20, h11 = a20.length - 1, c16; h11 >= 0; h11--)
    (c16 = a20[h11]) && (t20 = (s16 ? c16(o20, l10, t20) : c16(t20)) || t20);
  return s16 && t20 && d9(o20, l10, t20), t20;
};
var e20 = class extends o5 {
  constructor() {
    super(...arguments), this.active = false, this.disabled = false, this.href = "", this.target = "";
  }
  render() {
    return this.href ? b2`
        <a
          part="item"
          href=${this.href}
          target=${this.target || A}
          aria-current=${this.active ? "page" : A}
          aria-disabled=${this.disabled ? "true" : A}
          @click=${this._handleClick}
        >
          <slot name="prefix"></slot>
          <slot></slot>
          <span class="suffix"><slot name="suffix"></slot></span>
        </a>
      ` : b2`
      <button
        part="item"
        ?disabled=${this.disabled}
        aria-current=${this.active ? "page" : A}
        @click=${this._handleClick}
      >
        <slot name="prefix"></slot>
        <slot></slot>
        <span class="suffix"><slot name="suffix"></slot></span>
      </button>
    `;
  }
  _handleClick(a20) {
    if (this.disabled) {
      a20.preventDefault(), a20.stopPropagation();
      return;
    }
    this.dispatchEvent(
      new CustomEvent("bh-click", {
        bubbles: true,
        composed: true,
        detail: { originalEvent: a20 }
      })
    );
  }
};
e20.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }

      a,
      button {
        display: flex;
        align-items: center;
        gap: var(--bh-spacing-2);
        width: 100%;
        padding: var(--bh-spacing-2) var(--bh-spacing-3);
        border: none;
        border-radius: var(--bh-radius-md);
        background: var(--bh-nav-item-bg, transparent);
        color: var(--bh-nav-item-color, var(--bh-color-text));
        font-family: var(--bh-font-sans);
        font-size: var(--bh-text-base);
        font-weight: var(--bh-font-normal);
        line-height: var(--bh-leading-normal);
        text-decoration: none;
        cursor: pointer;
        transition: background var(--bh-transition-fast),
                    color var(--bh-transition-fast);
      }

      a:hover,
      button:hover {
        background: var(--bh-nav-item-hover-bg, var(--bh-color-secondary));
      }

      a:focus-visible,
      button:focus-visible {
        outline: 2px solid var(--bh-color-ring);
        outline-offset: -2px;
      }

      /* Active */
      :host([active]) a,
      :host([active]) button {
        background: var(--bh-nav-item-active-bg, var(--bh-color-secondary));
        color: var(--bh-nav-item-active-color, var(--bh-color-primary));
        font-weight: var(--bh-font-medium);
      }

      /* Disabled */
      :host([disabled]) a,
      :host([disabled]) button {
        opacity: 0.5;
        cursor: not-allowed;
        pointer-events: none;
      }

      /* Suffix pushed to end */
      .suffix {
        margin-left: auto;
      }
    `
];
r15([
  n5({ type: Boolean, reflect: true })
], e20.prototype, "active", 2);
r15([
  n5({ type: Boolean, reflect: true })
], e20.prototype, "disabled", 2);
r15([
  n5()
], e20.prototype, "href", 2);
r15([
  n5()
], e20.prototype, "target", 2);
e20 = r15([
  t3("bh-nav-item")
], e20);

// dist/molecules/table/bh-table.js
var v15 = Object.defineProperty;
var y4 = Object.getOwnPropertyDescriptor;
var o14 = (r28, t20, h11, s16) => {
  for (var a20 = s16 > 1 ? void 0 : s16 ? y4(t20, h11) : t20, l10 = r28.length - 1, i20; l10 >= 0; l10--)
    (i20 = r28[l10]) && (a20 = (s16 ? i20(t20, h11, a20) : i20(a20)) || a20);
  return s16 && a20 && v15(t20, h11, a20), a20;
};
var e21 = class extends o5 {
  constructor() {
    super(...arguments), this.variant = "default", this.density = "default", this.stickyHeader = false, this.columns = [], this.rows = [];
  }
  _renderHeaderCell(r28) {
    return b2`
      <th
        part="th"
        class=${r28.align ? `align-${r28.align}` : ""}
        style=${r28.width ? `width: ${r28.width}` : ""}
      >
        ${r28.label}
      </th>
    `;
  }
  get _displayRows() {
    return this.rows;
  }
  render() {
    return b2`
      <div class="wrapper">
        <table part="table">
          <thead part="thead">
            <tr>
              ${this.columns.map((r28) => this._renderHeaderCell(r28))}
            </tr>
          </thead>
          <tbody part="tbody">
            ${this._displayRows.map(
      (r28) => b2`
                <tr part="row">
                  ${this.columns.map(
        (t20) => b2`
                      <td
                        part="td"
                        class=${t20.align ? `align-${t20.align}` : ""}
                      >
                        ${String(r28[t20.key] ?? "")}
                      </td>
                    `
      )}
                </tr>
              `
    )}
          </tbody>
        </table>
      </div>
    `;
  }
};
e21.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }

      .wrapper {
        overflow-x: auto;
        border-radius: var(--bh-table-radius, var(--bh-radius-lg));
        border: var(--bh-border-1) solid var(--bh-table-border, var(--bh-color-border));
      }

      table {
        width: 100%;
        border-collapse: collapse;
        background: var(--bh-table-bg, var(--bh-color-surface-raised));
        font-family: var(--bh-font-sans);
        font-size: var(--bh-text-sm);
        line-height: var(--bh-leading-normal);
      }

      /* Header */
      thead {
        background: var(--bh-table-header-bg, var(--bh-color-surface));
      }

      th {
        font-weight: var(--bh-font-semibold);
        color: var(--bh-color-text-muted);
        text-align: left;
        white-space: nowrap;
        border-bottom: var(--bh-border-1) solid var(--bh-table-border, var(--bh-color-border));
      }

      /* Body */
      td {
        color: var(--bh-color-text);
        border-bottom: var(--bh-border-1) solid var(--bh-table-border, var(--bh-color-border));
      }

      tbody tr:last-child td {
        border-bottom: none;
      }

      /* Hover */
      tbody tr:hover {
        background: var(--bh-table-hover-bg, var(--bh-color-secondary));
      }

      /* Density — default */
      th,
      td,
      :host([density='default']) th,
      :host([density='default']) td {
        padding: var(--bh-spacing-3) var(--bh-spacing-4);
      }

      /* Density — compact */
      :host([density='compact']) th,
      :host([density='compact']) td {
        padding: var(--bh-spacing-1-5) var(--bh-spacing-3);
        font-size: var(--bh-text-xs);
      }

      /* Density — comfortable */
      :host([density='comfortable']) th,
      :host([density='comfortable']) td {
        padding: var(--bh-spacing-4) var(--bh-spacing-6);
      }

      /* Striped */
      :host([variant='striped']) tbody tr:nth-child(even) {
        background: var(--bh-table-stripe-bg, var(--bh-color-surface));
      }

      /* Bordered */
      :host([variant='bordered']) th,
      :host([variant='bordered']) td {
        border: var(--bh-border-1) solid var(--bh-table-border, var(--bh-color-border));
      }

      /* Alignment */
      .align-center {
        text-align: center;
      }

      .align-end {
        text-align: right;
      }

      /* Sticky header */
      :host([sticky-header]) thead th {
        position: sticky;
        top: 0;
        z-index: 1;
        background: var(--bh-table-header-bg, var(--bh-color-surface));
      }
    `
];
o14([
  n5({ reflect: true })
], e21.prototype, "variant", 2);
o14([
  n5({ reflect: true })
], e21.prototype, "density", 2);
o14([
  n5({ type: Boolean, reflect: true, attribute: "sticky-header" })
], e21.prototype, "stickyHeader", 2);
o14([
  n5({ type: Array })
], e21.prototype, "columns", 2);
o14([
  n5({ type: Array })
], e21.prototype, "rows", 2);
e21 = o14([
  t3("bh-table")
], e21);

// dist/molecules/pixel-panel/pixel-data-controller.js
var n10 = class {
  constructor(e31, i20) {
    this._buffer = [], this._text = "", this._host = e31, this._cols = i20.cols, this._rows = i20.rows, this._type = i20.type, this._color = i20.color ?? 1, this._bufferSize = i20.bufferSize ?? i20.cols, this._grid = new Uint8Array(i20.cols * i20.rows), e31.addController(this);
  }
  hostConnected() {
  }
  hostDisconnected() {
  }
  get grid() {
    return this._grid;
  }
  get latest() {
    return this._buffer.length > 0 ? this._buffer[this._buffer.length - 1] : void 0;
  }
  get values() {
    return this._buffer.slice();
  }
  push(e31) {
    this._buffer.push(e31), this._buffer.length > this._bufferSize && (this._buffer = this._buffer.slice(this._buffer.length - this._bufferSize)), this._regenerate();
  }
  set(e31) {
    this._buffer = e31.slice(-this._bufferSize), this._regenerate();
  }
  setText(e31) {
    this._text = e31, this._regenerate();
  }
  setGrid(e31) {
    this._applyGrid(e31);
  }
  resize(e31, i20) {
    this._cols = e31, this._rows = i20, this._grid = new Uint8Array(e31 * i20), this._regenerate();
  }
  configure(e31) {
    let i20 = false;
    e31.cols !== void 0 && e31.cols !== this._cols && (this._cols = e31.cols, i20 = true), e31.rows !== void 0 && e31.rows !== this._rows && (this._rows = e31.rows, i20 = true), e31.type !== void 0 && e31.type !== this._type && (this._type = e31.type, i20 = true), e31.color !== void 0 && e31.color !== this._color && (this._color = e31.color, i20 = true), e31.bufferSize !== void 0 && e31.bufferSize !== this._bufferSize && (this._bufferSize = e31.bufferSize, this._buffer.length > this._bufferSize && (this._buffer = this._buffer.slice(this._buffer.length - this._bufferSize)), i20 = true), i20 && (this._grid = new Uint8Array(this._cols * this._rows), this._regenerate());
  }
  _regenerate() {
    const { _cols: e31, _rows: i20, _color: t20, _type: s16 } = this;
    if (e31 === 0 || i20 === 0) return;
    let r28;
    switch (s16) {
      case "sparkline":
        r28 = s4(this._buffer, e31, i20, t20);
        break;
      case "bar":
        r28 = u3(this._buffer.length > 0 ? this._buffer[this._buffer.length - 1] : 0, e31, i20, t20);
        break;
      case "text":
        r28 = T2(this._text, e31, i20, t20);
        break;
      case "raw":
        return;
    }
    this._applyGrid(r28);
  }
  _applyGrid(e31) {
    const i20 = this._grid, t20 = Math.min(i20.length, e31.length);
    let s16 = i20.length !== e31.length;
    if (!s16) {
      for (let r28 = 0; r28 < t20; r28++)
        if (i20[r28] !== e31[r28]) {
          s16 = true;
          break;
        }
    }
    s16 && (this._grid = e31, this._host.requestUpdate());
  }
};

// node_modules/lit-html/async-directive.js
var s8 = (i20, t20) => {
  const e31 = i20._$AN;
  if (void 0 === e31) return false;
  for (const i21 of e31) i21._$AO?.(t20, false), s8(i21, t20);
  return true;
};
var o15 = (i20) => {
  let t20, e31;
  do {
    if (void 0 === (t20 = i20._$AM)) break;
    e31 = t20._$AN, e31.delete(i20), i20 = t20;
  } while (0 === e31?.size);
};
var r16 = (i20) => {
  for (let t20; t20 = i20._$AM; i20 = t20) {
    let e31 = t20._$AN;
    if (void 0 === e31) t20._$AN = e31 = /* @__PURE__ */ new Set();
    else if (e31.has(i20)) break;
    e31.add(i20), c7(t20);
  }
};
function h5(i20) {
  void 0 !== this._$AN ? (o15(this), this._$AM = i20, r16(this)) : this._$AM = i20;
}
function n11(i20, t20 = false, e31 = 0) {
  const r28 = this._$AH, h11 = this._$AN;
  if (void 0 !== h11 && 0 !== h11.size) if (t20) if (Array.isArray(r28)) for (let i21 = e31; i21 < r28.length; i21++) s8(r28[i21], false), o15(r28[i21]);
  else null != r28 && (s8(r28, false), o15(r28));
  else s8(this, i20);
}
var c7 = (i20) => {
  i20.type == t6.CHILD && (i20._$AP ??= n11, i20._$AQ ??= h5);
};
var f10 = class extends i9 {
  constructor() {
    super(...arguments), this._$AN = void 0;
  }
  _$AT(i20, t20, e31) {
    super._$AT(i20, t20, e31), r16(this), this.isConnected = i20._$AU;
  }
  _$AO(i20, t20 = true) {
    i20 !== this.isConnected && (this.isConnected = i20, i20 ? this.reconnected?.() : this.disconnected?.()), t20 && (s8(this, i20), o15(this));
  }
  setValue(t20) {
    if (r8(this._$Ct)) this._$Ct._$AI(t20, this);
    else {
      const i20 = [...this._$Ct._$AH];
      i20[this._$Ci] = t20, this._$Ct._$AI(i20, this, 0);
    }
  }
  disconnected() {
  }
  reconnected() {
  }
};

// dist/molecules/pixel-panel/animate-pixels.js
var f11 = class extends f10 {
  constructor(e31) {
    super(e31), this._fps = 12, this._cols = 0, this._sweepCursor = 0, this._sweepSpeed = 1, this._rafId = 0, this._pending = false, this._stepRafId = 0, this._tickSweep = () => {
      if (!this._target || !this._prev) return;
      this._sweepCursor += this._sweepSpeed;
      const t20 = this._cols, n14 = this._target.length / t20;
      if (this._sweepCursor >= t20) {
        this._current = this._target, this.setValue(this._target), this._prev = void 0, this._target = void 0, this._rafId = 0;
        return;
      }
      const r28 = new Uint8Array(this._target.length);
      for (let s16 = 0; s16 < n14; s16++)
        for (let h11 = 0; h11 < t20; h11++) {
          const _4 = s16 * t20 + h11;
          r28[_4] = h11 < this._sweepCursor ? this._target[_4] : this._prev[_4];
        }
      this.setValue(r28), this._rafId = requestAnimationFrame(this._tickSweep);
    };
  }
  render(e31, t20) {
    const n14 = (t20 == null ? void 0 : t20.transition) ?? "step", r28 = (t20 == null ? void 0 : t20.fps) ?? 12, s16 = (t20 == null ? void 0 : t20.cols) ?? 0;
    return this._fps = r28, this._cols = s16, n14 === "sweep" && s16 > 0 ? this._handleSweep(e31) : this._handleStep(e31);
  }
  _handleStep(e31) {
    return this._current ? e31 === this._current ? E : (this._target = e31, this._pending ? E : (this._pending = true, this._stepRafId = requestAnimationFrame(() => {
      this._stepRafId = 0, this._pending = false;
      const t20 = this._target;
      this._current = t20, this._target = void 0, this.setValue(t20);
    }), E)) : (this._current = e31, e31);
  }
  _handleSweep(e31) {
    return this._current ? e31 === this._current ? E : (this._cancelSweep(), this._prev = this._current, this._target = e31, this._sweepCursor = 0, this._sweepSpeed = Math.ceil(this._cols / Math.ceil(0.3 * this._fps)), this._tickSweep(), E) : (this._current = e31, e31);
  }
  _cancelSweep() {
    this._rafId && (cancelAnimationFrame(this._rafId), this._rafId = 0);
  }
  disconnected() {
    this._cancelSweep(), this._stepRafId && (cancelAnimationFrame(this._stepRafId), this._stepRafId = 0);
  }
  reconnected() {
    this._target && this._prev && this._sweepCursor < this._cols && (this._rafId = requestAnimationFrame(this._tickSweep));
  }
};
var d10 = e9(f11);

// dist/molecules/pixel-panel/bh-pixel-panel.js
var v16 = Object.defineProperty;
var m8 = Object.getOwnPropertyDescriptor;
var s9 = (t20, e31, l10, i20) => {
  for (var a20 = i20 > 1 ? void 0 : i20 ? m8(e31, l10) : e31, p9 = t20.length - 1, n14; p9 >= 0; p9--)
    (n14 = t20[p9]) && (a20 = (i20 ? n14(e31, l10, a20) : n14(a20)) || a20);
  return i20 && a20 && v16(e31, l10, a20), a20;
};
var r17 = class extends o5 {
  constructor() {
    super(...arguments), this.label = "", this.value = "", this.footerStart = "", this.footerEnd = "", this.cols = 0, this.rows = 0, this.type = "sparkline", this.transition = "step", this.fps = 12, this.color = 1, this.bufferSize = 0;
  }
  get _managed() {
    return this.cols > 0 && this.rows > 0;
  }
  willUpdate(t20) {
    this._managed && (this._ctrl ? (t20.has("cols") || t20.has("rows") || t20.has("type") || t20.has("color") || t20.has("bufferSize")) && this._ctrl.configure({
      cols: this.cols,
      rows: this.rows,
      type: this.type,
      color: this.color,
      bufferSize: this.bufferSize || this.cols
    }) : this._ctrl = new n10(this, {
      cols: this.cols,
      rows: this.rows,
      type: this.type,
      color: this.color,
      bufferSize: this.bufferSize || this.cols
    }));
  }
  push(t20) {
    var e31;
    (e31 = this._ctrl) == null || e31.push(t20);
  }
  set(t20) {
    var e31;
    (e31 = this._ctrl) == null || e31.set(t20);
  }
  setText(t20) {
    var e31;
    (e31 = this._ctrl) == null || e31.setText(t20);
  }
  setGrid(t20) {
    var e31;
    (e31 = this._ctrl) == null || e31.setGrid(t20);
  }
  _renderDisplay() {
    return b2`
      <bh-pixel-display
        .cols=${this.cols}
        .rows=${this.rows}
        .data=${d10(this._ctrl.grid, {
      transition: this.transition,
      fps: this.fps,
      cols: this.cols
    })}
        label=${this.label}
      ></bh-pixel-display>
    `;
  }
  render() {
    return b2`
      <bh-card class="panel" part="panel" variant="outlined" padding="none" role="group" aria-label=${this.label || "panel"}>
        <div class="header" part="header">
          <span class="label" part="label"><slot name="label">${this.label}</slot></span>
          <span class="value" part="value"><slot name="value">${this.value}</slot></span>
        </div>
        <div class="body" part="body">
          ${this._managed ? this._renderDisplay() : b2`<slot></slot>`}
        </div>
        <div class="footer" part="footer">
          <span><slot name="footer-start">${this.footerStart}</slot></span>
          <span><slot name="footer-end">${this.footerEnd}</slot></span>
        </div>
      </bh-card>
    `;
  }
};
r17.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: inline-block;
      }

      bh-card {
        --bh-card-bg: var(--bh-pixel-panel-bg, var(--bh-color-surface));
        --bh-card-border: var(--bh-pixel-panel-border, var(--bh-color-border));
        --bh-card-radius: var(--bh-pixel-panel-radius, var(--bh-radius-lg));
        --bh-card-shadow: none;
      }

      .header {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: var(--bh-spacing-2);
        padding: var(--bh-spacing-2) var(--bh-spacing-3);
      }

      .label {
        font-family: var(--bh-font-mono);
        font-size: var(--bh-text-2xs);
        font-weight: var(--bh-font-semibold);
        letter-spacing: var(--bh-tracking-wider);
        text-transform: uppercase;
        color: var(--bh-color-text-muted);
      }

      .value {
        font-family: var(--bh-font-mono);
        font-size: var(--bh-text-2xs);
        font-weight: var(--bh-font-semibold);
        color: var(--bh-color-text);
      }

      .body {
        padding: 0 var(--bh-spacing-3) var(--bh-spacing-2);
      }

      .footer {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: var(--bh-spacing-2);
        padding: var(--bh-spacing-1-5) var(--bh-spacing-3);
        border-top: var(--bh-border-1) solid var(--bh-color-border-muted);
        font-family: var(--bh-font-mono);
        font-size: var(--bh-text-2xs);
        color: var(--bh-color-text-muted);
      }
    `
];
s9([
  n5()
], r17.prototype, "label", 2);
s9([
  n5()
], r17.prototype, "value", 2);
s9([
  n5({ attribute: "footer-start" })
], r17.prototype, "footerStart", 2);
s9([
  n5({ attribute: "footer-end" })
], r17.prototype, "footerEnd", 2);
s9([
  n5({ type: Number })
], r17.prototype, "cols", 2);
s9([
  n5({ type: Number })
], r17.prototype, "rows", 2);
s9([
  n5()
], r17.prototype, "type", 2);
s9([
  n5()
], r17.prototype, "transition", 2);
s9([
  n5({ type: Number })
], r17.prototype, "fps", 2);
s9([
  n5({ type: Number })
], r17.prototype, "color", 2);
s9([
  n5({ type: Number, attribute: "buffer-size" })
], r17.prototype, "bufferSize", 2);
r17 = s9([
  t3("bh-pixel-panel")
], r17);

// dist/molecules/section-header/bh-section-header.js
var m9 = Object.defineProperty;
var v17 = Object.getOwnPropertyDescriptor;
var h6 = (r28, a20, s16, o20) => {
  for (var e31 = o20 > 1 ? void 0 : o20 ? v17(a20, s16) : a20, i20 = r28.length - 1, n14; i20 >= 0; i20--)
    (n14 = r28[i20]) && (e31 = (o20 ? n14(a20, s16, e31) : n14(e31)) || e31);
  return o20 && e31 && m9(a20, s16, e31), e31;
};
var t15 = class extends o5 {
  constructor() {
    super(...arguments), this.heading = "";
  }
  render() {
    const r28 = this.count !== void 0;
    return b2`
      <div class="header" part="header">
        <span class="title" part="title" role="heading" aria-level="3">
          <slot>${this.heading}</slot>
        </span>
        ${r28 ? b2`<span part="badge"><slot name="badge"><bh-badge size="sm" variant="primary">${this.count}</bh-badge></slot></span>` : b2`<slot name="badge"></slot>`}
        <bh-divider part="line"></bh-divider>
        <slot name="end"></slot>
      </div>
    `;
  }
};
t15.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }

      .header {
        display: flex;
        align-items: center;
        gap: var(--bh-spacing-2);
      }

      .title {
        font-family: var(--bh-font-mono);
        font-size: var(--bh-section-header-size, var(--bh-text-xs));
        font-weight: var(--bh-font-semibold);
        letter-spacing: var(--bh-section-header-tracking, var(--bh-tracking-widest));
        text-transform: uppercase;
        color: var(--bh-section-header-color, var(--bh-color-text-muted));
        white-space: nowrap;
      }

      bh-divider {
        flex: 1;
        padding: 0;
        --bh-divider-color: var(--bh-section-header-line-color, var(--bh-color-border-muted));
      }
    `
];
h6([
  n5()
], t15.prototype, "heading", 2);
h6([
  n5({ type: Number })
], t15.prototype, "count", 2);
t15 = h6([
  t3("bh-section-header")
], t15);

// dist/organisms/data-table/bh-data-table.js
var _2 = Object.defineProperty;
var m10 = Object.getOwnPropertyDescriptor;
var l6 = (t20, r28, s16, i20) => {
  for (var o20 = i20 > 1 ? void 0 : i20 ? m10(r28, s16) : r28, e31 = t20.length - 1, a20; e31 >= 0; e31--)
    (a20 = t20[e31]) && (o20 = (i20 ? a20(r28, s16, o20) : a20(o20)) || o20);
  return i20 && o20 && _2(r28, s16, o20), o20;
};
e11.register("sort-asc", '<path d="M12 19V5"/><path d="m5 12 7-7 7 7"/>');
e11.register("sort-desc", '<path d="M12 5v14"/><path d="m5 12 7 7 7-7"/>');
var n12 = class extends e21 {
  constructor() {
    super(...arguments), this._sortColumn = "", this._sortDirection = "none";
  }
  get _sortedRows() {
    if (this._sortDirection === "none" || !this._sortColumn)
      return this.rows;
    const t20 = this._sortColumn, r28 = this._sortDirection === "asc" ? 1 : -1;
    return [...this.rows].sort((s16, i20) => {
      const o20 = s16[t20], e31 = i20[t20];
      return o20 == null && e31 == null ? 0 : o20 == null ? 1 : e31 == null ? -1 : typeof o20 == "number" && typeof e31 == "number" ? (o20 - e31) * r28 : String(o20).localeCompare(String(e31)) * r28;
    });
  }
  get _displayRows() {
    return this._sortedRows;
  }
  _renderHeaderCell(t20) {
    if (!t20.sortable)
      return super._renderHeaderCell(t20);
    const s16 = this._sortColumn === t20.key && this._sortDirection !== "none";
    return b2`
      <th
        part="th"
        class=${t20.align ? `align-${t20.align}` : ""}
        style=${t20.width ? `width: ${t20.width}` : ""}
        aria-sort=${s16 ? this._sortDirection === "asc" ? "ascending" : "descending" : A}
      >
        <button
          class="sort-button"
          part="sort-button"
          @click=${() => this._onSortClick(t20.key)}
        >
          ${t20.label}
          <span class="sort-icon ${s16 ? "active" : ""}">
            <bh-icon name=${s16 && this._sortDirection === "desc" ? "sort-desc" : "sort-asc"}></bh-icon>
          </span>
        </button>
      </th>
    `;
  }
  _onSortClick(t20) {
    let r28;
    this._sortColumn === t20 ? this._sortDirection === "none" ? r28 = "asc" : this._sortDirection === "asc" ? r28 = "desc" : r28 = "none" : r28 = "asc", this._sortColumn = t20, this._sortDirection = r28, this.dispatchEvent(
      new CustomEvent("bh-sort", {
        bubbles: true,
        composed: true,
        detail: { column: t20, direction: r28 }
      })
    );
  }
};
n12.styles = [
  ...[e21.styles].flat(),
  i`
      /* Sort button */
      .sort-button {
        display: inline-flex;
        align-items: center;
        gap: var(--bh-spacing-1);
        padding: 0;
        border: none;
        background: none;
        color: inherit;
        font: inherit;
        font-weight: inherit;
        cursor: pointer;
        white-space: nowrap;
      }

      .sort-button:hover {
        color: var(--bh-color-text);
      }

      .sort-button:focus-visible {
        outline: 2px solid var(--bh-color-ring);
        outline-offset: 2px;
        border-radius: var(--bh-radius-sm);
      }

      /* Sort icons */
      .sort-icon {
        display: inline-flex;
        flex-shrink: 0;
        opacity: 0.3;
        transition: opacity var(--bh-transition-fast);
      }

      .sort-icon.active {
        opacity: 1;
      }

      .sort-icon bh-icon {
        --bh-icon-size: 1em;
      }
    `
];
l6([
  r5()
], n12.prototype, "_sortColumn", 2);
l6([
  r5()
], n12.prototype, "_sortDirection", 2);
n12 = l6([
  t3("bh-data-table")
], n12);

// dist/organisms/tabs/bh-tab.js
var u10 = Object.defineProperty;
var d11 = Object.getOwnPropertyDescriptor;
var a10 = (n14, o20, l10, e31) => {
  for (var t20 = e31 > 1 ? void 0 : e31 ? d11(o20, l10) : o20, s16 = n14.length - 1, b20; s16 >= 0; s16--)
    (b20 = n14[s16]) && (t20 = (e31 ? b20(o20, l10, t20) : b20(t20)) || t20);
  return e31 && t20 && u10(o20, l10, t20), t20;
};
var r18 = class extends o5 {
  constructor() {
    super(...arguments), this.tabId = "", this.label = "", this.active = false;
  }
  render() {
    return b2`
      <button
        part="button"
        role="tab"
        aria-selected=${this.active ? "true" : "false"}
        @click=${this._handleClick}
      >
        <slot>${this.label}</slot>
      </button>
    `;
  }
  _handleClick() {
    this.dispatchEvent(
      new CustomEvent("bh-tab-click", {
        bubbles: true,
        composed: true,
        detail: { tabId: this.tabId }
      })
    );
  }
};
r18.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }

      button {
        display: flex;
        align-items: center;
        padding: 0 var(--bh-spacing-4);
        height: 100%;
        background: transparent;
        border: none;
        border-bottom: var(--bh-border-2) solid transparent;
        color: var(--bh-tab-color, var(--bh-color-text-muted));
        font-family: var(--bh-font-sans);
        font-size: var(--bh-text-sm);
        cursor: pointer;
        white-space: nowrap;
        transition: color var(--bh-transition-fast);
      }

      button:hover {
        color: var(--bh-tab-active-color, var(--bh-color-text));
      }

      button:focus-visible {
        outline: 2px solid var(--bh-color-ring);
        outline-offset: -2px;
      }

      :host([active]) button {
        color: var(--bh-tab-active-color, var(--bh-color-text));
        border-bottom-color: var(--bh-tab-active-border, var(--bh-color-primary));
      }
    `
];
a10([
  n5({ attribute: "tab-id" })
], r18.prototype, "tabId", 2);
a10([
  n5()
], r18.prototype, "label", 2);
a10([
  n5({ type: Boolean, reflect: true })
], r18.prototype, "active", 2);
r18 = a10([
  t3("bh-tab")
], r18);

// dist/organisms/tabs/bh-tab-bar.js
var p6 = Object.defineProperty;
var m11 = Object.getOwnPropertyDescriptor;
var c8 = (t20, e31, r28, s16) => {
  for (var a20 = s16 > 1 ? void 0 : s16 ? m11(e31, r28) : e31, b20 = t20.length - 1, i20; b20 >= 0; b20--)
    (i20 = t20[b20]) && (a20 = (s16 ? i20(e31, r28, a20) : i20(a20)) || a20);
  return s16 && a20 && p6(e31, r28, a20), a20;
};
var o16 = class extends o5 {
  constructor() {
    super(...arguments), this.active = "";
  }
  render() {
    return b2`
      <div class="tabs" role="tablist" @bh-tab-click=${this._handleTabClick}>
        <slot @slotchange=${this._syncActive}></slot>
      </div>
    `;
  }
  updated(t20) {
    t20.has("active") && this._syncActive();
  }
  _syncActive() {
    const t20 = this._getTabs();
    for (const e31 of t20)
      e31.active = e31.tabId === this.active;
  }
  _handleTabClick(t20) {
    t20.stopPropagation(), this.active = t20.detail.tabId, this.dispatchEvent(
      new CustomEvent("bh-tab-change", {
        bubbles: true,
        composed: true,
        detail: { tabId: t20.detail.tabId }
      })
    );
  }
  _getTabs() {
    var e31;
    const t20 = (e31 = this.shadowRoot) == null ? void 0 : e31.querySelector("slot");
    return t20 ? t20.assignedElements({ flatten: true }).filter((r28) => r28.tagName === "BH-TAB") : [];
  }
};
o16.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }

      .tabs {
        display: flex;
        align-items: center;
        height: var(--bh-tab-bar-height, 36px);
        background: var(--bh-tab-bar-bg, transparent);
        border-bottom: var(--bh-border-1) solid var(--bh-tab-bar-border, var(--bh-color-border));
        overflow-x: auto;
      }

      ::slotted(bh-tab) {
        height: 100%;
      }
    `
];
c8([
  n5()
], o16.prototype, "active", 2);
o16 = c8([
  t3("bh-tab-bar")
], o16);

// dist/organisms/tabs/bh-tab-panel.js
var f12 = Object.defineProperty;
var m12 = Object.getOwnPropertyDescriptor;
var i13 = (p9, r28, o20, s16) => {
  for (var t20 = s16 > 1 ? void 0 : s16 ? m12(r28, o20) : r28, a20 = p9.length - 1, l10; a20 >= 0; a20--)
    (l10 = p9[a20]) && (t20 = (s16 ? l10(r28, o20, t20) : l10(t20)) || t20);
  return s16 && t20 && f12(r28, o20, t20), t20;
};
var e22 = class extends o5 {
  constructor() {
    super(...arguments), this.tabId = "", this.active = false;
  }
  connectedCallback() {
    super.connectedCallback(), this.hasAttribute("role") || this.setAttribute("role", "tabpanel"), this.hasAttribute("tabindex") || this.setAttribute("tabindex", "0");
  }
  render() {
    return b2`<slot></slot>`;
  }
};
e22.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: none;
        height: 100%;
        overflow: auto;
      }

      :host([active]) {
        display: block;
      }
    `
];
i13([
  n5({ attribute: "tab-id" })
], e22.prototype, "tabId", 2);
i13([
  n5({ type: Boolean, reflect: true })
], e22.prototype, "active", 2);
e22 = i13([
  t3("bh-tab-panel")
], e22);

// dist/organisms/tabs/bh-tabs.js
var d12 = Object.defineProperty;
var f13 = Object.getOwnPropertyDescriptor;
var c9 = (t20, e31, s16, n14) => {
  for (var a20 = n14 > 1 ? void 0 : n14 ? f13(e31, s16) : e31, l10 = t20.length - 1, o20; l10 >= 0; l10--)
    (o20 = t20[l10]) && (a20 = (n14 ? o20(e31, s16, a20) : o20(a20)) || a20);
  return n14 && a20 && d12(e31, s16, a20), a20;
};
var r19 = class extends o5 {
  constructor() {
    super(...arguments), this.active = "";
  }
  render() {
    return b2`
      <slot name="tab-bar" @bh-tab-change=${this._handleTabChange}></slot>
      <div class="panels">
        <slot @slotchange=${this._syncPanels}></slot>
      </div>
    `;
  }
  updated(t20) {
    t20.has("active") && (this._syncPanels(), this._syncTabBar());
  }
  _handleTabChange(t20) {
    t20.stopPropagation(), this.active = t20.detail.tabId, this.dispatchEvent(
      new CustomEvent("bh-tab-change", {
        bubbles: true,
        composed: true,
        detail: { tabId: t20.detail.tabId }
      })
    );
  }
  _syncPanels() {
    const t20 = this._getPanels();
    for (const e31 of t20)
      e31.active = e31.tabId === this.active;
  }
  _syncTabBar() {
    const t20 = this._getTabBar();
    t20 && (t20.active = this.active);
  }
  _getPanels() {
    var e31;
    const t20 = (e31 = this.shadowRoot) == null ? void 0 : e31.querySelector("slot:not([name])");
    return t20 ? t20.assignedElements({ flatten: true }).filter(
      (s16) => s16.tagName === "BH-TAB-PANEL"
    ) : [];
  }
  _getTabBar() {
    var s16;
    const t20 = (s16 = this.shadowRoot) == null ? void 0 : s16.querySelector('slot[name="tab-bar"]');
    return t20 ? t20.assignedElements({ flatten: true }).find(
      (n14) => n14.tagName === "BH-TAB-BAR"
    ) ?? null : null;
  }
};
r19.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: flex;
        flex-direction: column;
      }

      .panels {
        flex: 1;
        min-height: 0;
        overflow: hidden;
      }
    `
];
c9([
  n5()
], r19.prototype, "active", 2);
r19 = c9([
  t3("bh-tabs")
], r19);

// dist/organisms/shell/bh-app-shell.js
var b10 = Object.defineProperty;
var c10 = Object.getOwnPropertyDescriptor;
var h7 = (d19, s16, r28, i20) => {
  for (var t20 = i20 > 1 ? void 0 : i20 ? c10(s16, r28) : s16, a20 = d19.length - 1, l10; a20 >= 0; a20--)
    (l10 = d19[a20]) && (t20 = (i20 ? l10(s16, r28, t20) : l10(t20)) || t20);
  return i20 && t20 && b10(s16, r28, t20), t20;
};
var e23 = class extends o5 {
  constructor() {
    super(...arguments), this.sidebarOpen = false;
  }
  render() {
    return b2`
      <div class="grid" part="grid">
        <div class="activity">
          <slot name="activity"></slot>
        </div>
        <div class="sidebar">
          <slot name="sidebar"></slot>
        </div>
        <div class="main">
          <slot></slot>
        </div>
        <div class="status">
          <slot name="status"></slot>
        </div>
      </div>
    `;
  }
};
e23.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
        height: 100vh;
        width: 100vw;
        background: var(--bh-shell-bg, var(--bh-color-bg));
      }

      .grid {
        display: grid;
        grid-template-columns:
          var(--bh-shell-activity-width, 48px)
          var(--bh-shell-sidebar-width, 0px)
          1fr;
        grid-template-rows: 1fr var(--bh-shell-status-height, 24px);
        grid-template-areas:
          "activity sidebar main"
          "status   status  status";
        height: 100%;
        width: 100%;
        transition: grid-template-columns var(--bh-transition-normal);
      }

      :host([sidebar-open]) .grid {
        --bh-shell-sidebar-width: 250px;
      }

      .activity {
        grid-area: activity;
        min-width: 0;
      }

      .sidebar {
        grid-area: sidebar;
        min-width: 0;
        overflow: hidden;
      }

      .main {
        grid-area: main;
        min-width: 0;
        overflow: auto;
      }

      .status {
        grid-area: status;
        min-width: 0;
      }
    `
];
h7([
  n5({ type: Boolean, reflect: true, attribute: "sidebar-open" })
], e23.prototype, "sidebarOpen", 2);
e23 = h7([
  t3("bh-app-shell")
], e23);

// dist/organisms/shell/bh-activity-item.js
var d13 = Object.defineProperty;
var m13 = Object.getOwnPropertyDescriptor;
var i14 = (c16, r28, a20, o20) => {
  for (var t20 = o20 > 1 ? void 0 : o20 ? m13(r28, a20) : r28, l10 = c16.length - 1, s16; l10 >= 0; l10--)
    (s16 = c16[l10]) && (t20 = (o20 ? s16(r28, a20, t20) : s16(t20)) || t20);
  return o20 && t20 && d13(r28, a20, t20), t20;
};
var e24 = class extends o5 {
  constructor() {
    super(...arguments), this.active = false, this.label = "", this.itemId = "";
  }
  render() {
    return b2`
      <button
        part="button"
        title=${this.label || A}
        aria-label=${this.label || A}
        aria-pressed=${this.active ? "true" : "false"}
        @click=${this._handleClick}
      >
        <slot></slot>
      </button>
    `;
  }
  _handleClick() {
    this.dispatchEvent(
      new CustomEvent("bh-activity-item-click", {
        bubbles: true,
        composed: true,
        detail: { id: this.itemId, label: this.label }
      })
    );
  }
};
e24.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }

      button {
        display: flex;
        align-items: center;
        justify-content: center;
        width: var(--bh-activity-item-size, 40px);
        height: var(--bh-activity-item-size, 40px);
        background: none;
        border: none;
        border-left: var(--bh-border-2) solid transparent;
        border-radius: 0;
        color: var(--bh-color-text-muted);
        cursor: pointer;
        padding: 0;
        transition: color var(--bh-transition-fast), background var(--bh-transition-fast);
      }

      button:hover {
        color: var(--bh-color-text);
      }

      button:focus-visible {
        outline: 2px solid var(--bh-color-ring);
        outline-offset: -2px;
      }

      :host([active]) button {
        color: var(--bh-color-text);
        border-left-color: var(--bh-activity-item-active-border, var(--bh-color-primary));
        background: var(--bh-color-surface);
      }
    `
];
i14([
  n5({ type: Boolean, reflect: true })
], e24.prototype, "active", 2);
i14([
  n5()
], e24.prototype, "label", 2);
i14([
  n5({ attribute: "item-id" })
], e24.prototype, "itemId", 2);
e24 = i14([
  t3("bh-activity-item")
], e24);

// dist/organisms/shell/bh-activity-bar.js
var b11 = Object.defineProperty;
var p7 = Object.getOwnPropertyDescriptor;
var d14 = (e31, i20, r28, t20) => {
  for (var s16 = t20 > 1 ? void 0 : t20 ? p7(i20, r28) : i20, c16 = e31.length - 1, o20; c16 >= 0; c16--)
    (o20 = e31[c16]) && (s16 = (t20 ? o20(i20, r28, s16) : o20(s16)) || s16);
  return t20 && s16 && b11(i20, r28, s16), s16;
};
var a11 = class extends o5 {
  constructor() {
    super(...arguments), this._activeId = "";
  }
  render() {
    return b2`
      <div class="items" part="container" @bh-activity-item-click=${this._handleItemClick}>
        <slot></slot>
      </div>
    `;
  }
  get activeId() {
    return this._activeId;
  }
  setActive(e31) {
    this._activeId = e31, this._updateItems();
  }
  _handleItemClick(e31) {
    const { id: i20, label: r28 } = e31.detail, t20 = this._activeId === i20;
    this._activeId = t20 ? "" : i20, this._updateItems(), this.dispatchEvent(
      new CustomEvent("bh-activity-change", {
        bubbles: true,
        composed: true,
        detail: {
          id: this._activeId,
          label: this._activeId ? r28 : ""
        }
      })
    );
  }
  _updateItems() {
    var r28;
    const e31 = (r28 = this.shadowRoot) == null ? void 0 : r28.querySelector("slot");
    if (!e31) return;
    const i20 = e31.assignedElements({ flatten: true }).filter(
      (t20) => t20.tagName === "BH-ACTIVITY-ITEM"
    );
    for (const t20 of i20)
      t20.active = t20.itemId === this._activeId;
  }
};
a11.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: flex;
        flex-direction: column;
        width: var(--bh-activity-bar-width, 48px);
        background: var(--bh-activity-bar-bg, var(--bh-color-surface-recessed));
        border-right: var(--bh-border-1) solid var(--bh-activity-bar-border, var(--bh-color-border));
        padding-top: var(--bh-spacing-2);
      }

      .items {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: var(--bh-spacing-1);
      }
    `
];
d14([
  r5()
], a11.prototype, "_activeId", 2);
a11 = d14([
  t3("bh-activity-bar")
], a11);

// dist/organisms/shell/bh-sidebar-panel.js
var v18 = Object.defineProperty;
var f14 = Object.getOwnPropertyDescriptor;
var h8 = (r28, a20, o20, t20) => {
  for (var e31 = t20 > 1 ? void 0 : t20 ? f14(a20, o20) : a20, l10 = r28.length - 1, d19; l10 >= 0; l10--)
    (d19 = r28[l10]) && (e31 = (t20 ? d19(a20, o20, e31) : d19(e31)) || e31);
  return t20 && e31 && v18(a20, o20, e31), e31;
};
var s10 = class extends o5 {
  constructor() {
    super(...arguments), this.collapsed = false, this._firstUpdate = true;
  }
  render() {
    return b2`
      <div class="header" part="header">
        <slot name="header"></slot>
      </div>
      <div class="body" part="body">
        <slot></slot>
      </div>
    `;
  }
  updated(r28) {
    if (this._firstUpdate) {
      this._firstUpdate = false;
      return;
    }
    r28.has("collapsed") && this.dispatchEvent(
      new CustomEvent("bh-sidebar-collapse", {
        bubbles: true,
        composed: true,
        detail: { collapsed: this.collapsed }
      })
    );
  }
};
s10.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
        width: var(--bh-sidebar-panel-width, 250px);
        background: var(--bh-sidebar-panel-bg, var(--bh-color-surface));
        border-right: var(--bh-border-1) solid var(--bh-sidebar-panel-border, var(--bh-color-border));
        overflow: hidden;
        transition: width var(--bh-transition-normal);
      }

      :host([collapsed]) {
        width: 0;
      }

      .header {
        display: flex;
        align-items: center;
        height: var(--bh-spacing-9);
        padding: 0 var(--bh-spacing-3);
        border-bottom: var(--bh-border-1) solid var(--bh-sidebar-panel-border, var(--bh-color-border));
        flex-shrink: 0;
      }

      .body {
        overflow-y: auto;
        height: calc(100% - var(--bh-spacing-9));
      }
    `
];
h8([
  n5({ type: Boolean, reflect: true })
], s10.prototype, "collapsed", 2);
s10 = h8([
  t3("bh-sidebar-panel")
], s10);

// dist/organisms/shell/bh-status-bar.js
var d15 = Object.defineProperty;
var g10 = Object.getOwnPropertyDescriptor;
var i15 = (n14, s16, a20, t20) => {
  for (var e31 = t20 > 1 ? void 0 : t20 ? g10(s16, a20) : s16, o20 = n14.length - 1, l10; o20 >= 0; o20--)
    (l10 = n14[o20]) && (e31 = (t20 ? l10(s16, a20, e31) : l10(e31)) || e31);
  return t20 && e31 && d15(s16, a20, e31), e31;
};
var r20 = class extends o5 {
  constructor() {
    super(...arguments), this.message = "", this.error = false;
  }
  render() {
    return b2`
      <div class="bar" part="bar" role="status" aria-live="polite">
        <div class="start">
          ${this.message ? b2`<span class="message">${this.message}</span>` : ""}
          <slot></slot>
        </div>
        <div class="end">
          <slot name="end"></slot>
        </div>
      </div>
    `;
  }
};
r20.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
        height: var(--bh-spacing-6);
        background: var(--bh-status-bar-bg, var(--bh-color-surface));
        border-top: var(--bh-border-1) solid var(--bh-status-bar-border, var(--bh-color-border));
        color: var(--bh-status-bar-text, var(--bh-color-text-muted));
        font-size: var(--bh-text-xs);
        line-height: var(--bh-spacing-6);
      }

      .bar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        height: 100%;
        padding: 0 var(--bh-spacing-3);
        gap: var(--bh-spacing-2);
      }

      .start,
      .end {
        display: flex;
        align-items: center;
        gap: var(--bh-spacing-2);
        min-width: 0;
      }

      .start {
        flex: 1;
        overflow: hidden;
      }

      .end {
        flex-shrink: 0;
      }

      .message {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      :host([error]) {
        color: var(--bh-status-bar-error-text, var(--bh-color-danger));
      }
    `
];
i15([
  n5()
], r20.prototype, "message", 2);
i15([
  n5({ type: Boolean, reflect: true })
], r20.prototype, "error", 2);
r20 = i15([
  t3("bh-status-bar")
], r20);

// dist/molecules/panel-header/bh-panel-header.js
var v19 = Object.defineProperty;
var f15 = Object.getOwnPropertyDescriptor;
var o17 = (p9, t20, s16, r28) => {
  for (var e31 = r28 > 1 ? void 0 : r28 ? f15(t20, s16) : t20, l10 = p9.length - 1, n14; l10 >= 0; l10--)
    (n14 = p9[l10]) && (e31 = (r28 ? n14(t20, s16, e31) : n14(e31)) || e31);
  return r28 && e31 && v19(t20, s16, e31), e31;
};
var a12 = class extends o5 {
  constructor() {
    super(...arguments), this.label = "";
  }
  render() {
    return b2`
      <div class="header" part="header">
        <span class="label" part="label">${this.label}</span>
        <div class="end">
          <slot name="end"></slot>
        </div>
      </div>
    `;
  }
};
a12.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }

      .header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        height: var(--bh-panel-header-height, 36px);
        padding: 0 var(--bh-spacing-3);
        gap: var(--bh-spacing-2);
      }

      .label {
        font-size: var(--bh-text-xs);
        font-weight: var(--bh-font-semibold);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--bh-panel-header-text, var(--bh-color-text-muted));
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        min-width: 0;
      }

      .end {
        display: flex;
        align-items: center;
        gap: var(--bh-spacing-1);
        flex-shrink: 0;
      }
    `
];
o17([
  n5()
], a12.prototype, "label", 2);
a12 = o17([
  t3("bh-panel-header")
], a12);

// dist/molecules/toolbar/bh-toolbar.js
var h9 = Object.defineProperty;
var g11 = Object.getOwnPropertyDescriptor;
var e25 = (p9, a20, s16, o20) => {
  for (var t20 = o20 > 1 ? void 0 : o20 ? g11(a20, s16) : a20, l10 = p9.length - 1, i20; l10 >= 0; l10--)
    (i20 = p9[l10]) && (t20 = (o20 ? i20(a20, s16, t20) : i20(t20)) || t20);
  return o20 && t20 && h9(a20, s16, t20), t20;
};
var r21 = class extends o5 {
  constructor() {
    super(...arguments), this.gap = "sm", this.variant = "default", this.sticky = false;
  }
  render() {
    return b2`
      <div class="toolbar" part="toolbar" role="toolbar">
        <div class="start"><slot name="start"></slot></div>
        <div class="center"><slot></slot></div>
        <div class="end"><slot name="end"></slot></div>
      </div>
    `;
  }
};
r21.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }

      .toolbar {
        display: flex;
        align-items: center;
        padding: var(--bh-spacing-2) var(--bh-spacing-4);
      }

      /* Variant: surface */
      :host([variant='surface']) .toolbar {
        background: var(--bh-toolbar-bg, var(--bh-color-surface));
      }

      /* Sticky border */
      :host([sticky]) {
        position: sticky;
        top: 0;
        z-index: var(--bh-z-sticky);
      }

      :host([sticky]) .toolbar {
        border-bottom: var(--bh-border-1) solid var(--bh-toolbar-border, var(--bh-color-border));
      }

      /* Gap sizes */
      .toolbar {
        gap: var(--bh-spacing-2);
      }

      :host([gap='xs']) .toolbar {
        gap: var(--bh-spacing-1);
      }

      :host([gap='sm']) .toolbar {
        gap: var(--bh-spacing-2);
      }

      :host([gap='md']) .toolbar {
        gap: var(--bh-spacing-4);
      }

      /* Sections */
      .start,
      .center,
      .end {
        display: flex;
        align-items: center;
        gap: inherit;
      }

      .start {
        margin-inline-end: auto;
      }

      .center {
        flex: 1;
        justify-content: center;
      }

      .end {
        margin-inline-start: auto;
      }
    `
];
e25([
  n5({ reflect: true })
], r21.prototype, "gap", 2);
e25([
  n5({ reflect: true })
], r21.prototype, "variant", 2);
e25([
  n5({ type: Boolean, reflect: true })
], r21.prototype, "sticky", 2);
r21 = e25([
  t3("bh-toolbar")
], r21);

// dist/molecules/accordion/bh-accordion.js
var v20 = Object.defineProperty;
var f16 = Object.getOwnPropertyDescriptor;
var a13 = (r28, o20, n14, e31) => {
  for (var t20 = e31 > 1 ? void 0 : e31 ? f16(o20, n14) : o20, c16 = r28.length - 1, d19; c16 >= 0; c16--)
    (d19 = r28[c16]) && (t20 = (e31 ? d19(o20, n14, t20) : d19(t20)) || t20);
  return e31 && t20 && v20(o20, n14, t20), t20;
};
var l7 = class extends o5 {
  constructor() {
    super(...arguments), this.multiple = false;
  }
  connectedCallback() {
    super.connectedCallback(), this.addEventListener("bh-toggle", this._handleItemToggle);
  }
  disconnectedCallback() {
    super.disconnectedCallback(), this.removeEventListener("bh-toggle", this._handleItemToggle);
  }
  _handleItemToggle(r28) {
    if (this.multiple || !r28.detail.open) return;
    const o20 = r28.composedPath().find(
      (e31) => e31.tagName === "BH-ACCORDION-ITEM"
    ), n14 = this.querySelectorAll("bh-accordion-item");
    for (const e31 of n14)
      e31 !== o20 && e31.open && (e31.open = false);
  }
  render() {
    return b2`<slot></slot>`;
  }
};
l7.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }
    `
];
a13([
  n5({ type: Boolean, reflect: true })
], l7.prototype, "multiple", 2);
l7 = a13([
  t3("bh-accordion")
], l7);
var s11 = class extends o5 {
  constructor() {
    super(...arguments), this.label = "", this.open = false;
  }
  render() {
    return b2`
      <button
        class="header"
        part="header"
        aria-expanded=${this.open}
        aria-controls="accordion-content"
        @click=${this._toggle}
      >
        <slot name="header">${this.label}</slot>
        <bh-icon class="chevron" part="chevron" name="chevron-right" size="sm" aria-hidden="true"></bh-icon>
      </button>
      <div class="content-wrapper">
        <div id="accordion-content" class="content" part="content">
          <div class="content-inner">
            <slot></slot>
          </div>
        </div>
      </div>
    `;
  }
  _toggle() {
    this.open = !this.open, this.dispatchEvent(
      new CustomEvent("bh-toggle", {
        bubbles: true,
        composed: true,
        detail: { open: this.open, label: this.label }
      })
    );
  }
};
s11.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
        border-bottom: var(--bh-border-1) solid var(--bh-accordion-border, var(--bh-color-border));
      }

      .header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: var(--bh-spacing-3) var(--bh-spacing-4);
        cursor: pointer;
        user-select: none;
        font-family: var(--bh-font-sans);
        font-size: var(--bh-text-sm);
        color: var(--bh-color-text);
        background: none;
        border: none;
        width: 100%;
        text-align: start;
      }

      .header:hover {
        background: var(--bh-color-surface);
      }

      .header:focus-visible {
        outline: var(--bh-border-2) solid var(--bh-color-ring);
        outline-offset: -2px;
      }

      .chevron {
        display: inline-flex;
        transition: transform var(--bh-transition-fast);
        color: var(--bh-color-text-muted);
        flex-shrink: 0;
      }

      :host([open]) .chevron {
        transform: rotate(90deg);
      }

      .content-wrapper {
        display: grid;
        grid-template-rows: 0fr;
        transition: grid-template-rows var(--bh-transition-fast);
      }

      :host([open]) .content-wrapper {
        grid-template-rows: 1fr;
      }

      .content {
        overflow: hidden;
      }

      .content-inner {
        padding: 0 var(--bh-spacing-4) var(--bh-spacing-3);
      }
    `
];
a13([
  n5()
], s11.prototype, "label", 2);
a13([
  n5({ type: Boolean, reflect: true })
], s11.prototype, "open", 2);
s11 = a13([
  t3("bh-accordion-item")
], s11);

// dist/molecules/terminal-bar/bh-terminal-bar.js
var d16 = Object.defineProperty;
var u11 = Object.getOwnPropertyDescriptor;
var a14 = (p9, s16, o20, r28) => {
  for (var t20 = r28 > 1 ? void 0 : r28 ? u11(s16, o20) : s16, l10 = p9.length - 1, i20; l10 >= 0; l10--)
    (i20 = p9[l10]) && (t20 = (r28 ? i20(s16, o20, t20) : i20(t20)) || t20);
  return r28 && t20 && d16(s16, o20, t20), t20;
};
var e26 = class extends o5 {
  constructor() {
    super(...arguments), this.title = "Terminal", this.status = "", this.statusColor = "success";
  }
  render() {
    return b2`
      <div class="bar" part="bar">
        <div class="bar-left">
          <bh-led color="danger" size="sm"></bh-led>
          <bh-led color="warning" size="sm"></bh-led>
          <bh-led color="success" size="sm"></bh-led>
          <span class="title" part="title">${this.title}</span>
        </div>
        <div class="bar-right">
          ${this.status ? b2`
                <span class="status" part="status">
                  <bh-led color=${this.statusColor} size="sm" pulse></bh-led>
                  ${this.status}
                </span>
              ` : A}
        </div>
      </div>
    `;
  }
};
e26.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }

      .bar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        height: var(--bh-terminal-bar-height, 32px);
        padding: 0 12px;
        background: var(--bh-terminal-bar-bg, var(--bh-color-surface-recessed));
        border-bottom: 1px solid var(--bh-color-border);
        box-shadow: var(--bh-shadow-emboss);
        user-select: none;
      }

      .bar-left {
        display: flex;
        align-items: center;
        gap: 6px;
      }

      .title {
        font-family: var(--bh-font-mono);
        font-size: 10px;
        font-weight: var(--bh-font-medium);
        letter-spacing: 2px;
        text-transform: uppercase;
        color: var(--bh-color-text-tertiary);
        margin-left: 8px;
      }

      .bar-right {
        display: flex;
        align-items: center;
      }

      .status {
        display: flex;
        align-items: center;
        gap: 5px;
        font-family: var(--bh-font-mono);
        font-size: 8px;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        color: var(--bh-color-text-tertiary);
      }
    `
];
a14([
  n5()
], e26.prototype, "title", 2);
a14([
  n5()
], e26.prototype, "status", 2);
a14([
  n5({ reflect: true, attribute: "status-color" })
], e26.prototype, "statusColor", 2);
e26 = a14([
  t3("bh-terminal-bar")
], e26);

// dist/molecules/terminal-input/bh-terminal-input.js
var y5 = Object.defineProperty;
var b12 = Object.getOwnPropertyDescriptor;
var s12 = (t20, e31, o20, i20) => {
  for (var p9 = i20 > 1 ? void 0 : i20 ? b12(e31, o20) : e31, a20 = t20.length - 1, h11; a20 >= 0; a20--)
    (h11 = t20[a20]) && (p9 = (i20 ? h11(e31, o20, p9) : h11(p9)) || p9);
  return i20 && p9 && y5(e31, o20, p9), p9;
};
var r22 = class extends o5 {
  constructor() {
    super(...arguments), this.prompt = "\u25B8 ", this.promptUser = "", this.promptPath = "~", this.disabled = false, this._history = [], this._historyIndex = -1, this._tempLine = "";
  }
  /** Focus the internal input element. */
  focus() {
    this.updateComplete.then(() => {
      var t20;
      (t20 = this._input) == null || t20.focus();
    });
  }
  _onKeydown(t20) {
    const e31 = this._input;
    if (t20.key === "Enter") {
      t20.preventDefault();
      const o20 = e31.value.trim();
      o20 && (this._history = [...this._history, o20], this._historyIndex = -1, this._tempLine = "", this.dispatchEvent(
        new CustomEvent("bh-command", { detail: o20, bubbles: true, composed: true })
      ), e31.value = "");
      return;
    }
    if (t20.key === "ArrowUp") {
      if (t20.preventDefault(), this._history.length === 0) return;
      this._historyIndex === -1 ? (this._tempLine = e31.value, this._historyIndex = this._history.length - 1) : this._historyIndex > 0 && this._historyIndex--, e31.value = this._history[this._historyIndex];
      return;
    }
    if (t20.key === "ArrowDown") {
      if (t20.preventDefault(), this._historyIndex === -1) return;
      this._historyIndex++, this._historyIndex >= this._history.length ? (this._historyIndex = -1, e31.value = this._tempLine, this._tempLine = "") : e31.value = this._history[this._historyIndex];
      return;
    }
    if (t20.key === "Tab") {
      t20.preventDefault(), this.dispatchEvent(
        new CustomEvent("bh-tab-complete", {
          detail: e31.value,
          bubbles: true,
          composed: true
        })
      );
      return;
    }
    if (t20.ctrlKey)
      switch (t20.key) {
        case "c":
          t20.preventDefault(), this.dispatchEvent(
            new CustomEvent("bh-interrupt", { bubbles: true, composed: true })
          ), e31.value = "";
          return;
        case "l":
          t20.preventDefault(), this.dispatchEvent(
            new CustomEvent("bh-clear", { bubbles: true, composed: true })
          );
          return;
        case "u":
          t20.preventDefault(), e31.value = "";
          return;
        case "k":
          t20.preventDefault(), e31.value = e31.value.substring(0, e31.selectionStart ?? 0);
          return;
        case "a":
          t20.preventDefault(), e31.setSelectionRange(0, 0);
          return;
        case "e":
          t20.preventDefault(), e31.setSelectionRange(e31.value.length, e31.value.length);
          return;
      }
  }
  render() {
    return b2`
      <div class="input-area" part="input-area">
        ${this.promptUser ? b2`
              <div class="prompt-line">
                <span class="prompt-chrome">\u250C\u2500[</span>
                <span class="prompt-user">${this.promptUser}</span>
                <span class="prompt-chrome">]\u2500[</span>
                <span class="prompt-path">${this.promptPath}</span>
                <span class="prompt-chrome">]</span>
              </div>
            ` : A}
        <div class="prompt-line">
          ${this.promptUser ? b2`<span class="prompt-chrome">\u2514\u2500</span>` : A}
          <span class="prompt-char" part="prompt">${this.prompt}</span>
          <input
            type="text"
            class="cmd-input"
            part="input"
            autocomplete="off"
            autocorrect="off"
            autocapitalize="off"
            spellcheck="false"
            ?disabled=${this.disabled}
            @keydown=${this._onKeydown}
          />
        </div>
      </div>
    `;
  }
};
r22.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }

      .input-area {
        background: var(--bh-color-bg, var(--bh-color-cod));
        padding: 0 16px 12px;
        flex-shrink: 0;
      }

      .prompt-line {
        display: flex;
        align-items: flex-start;
        font-family: var(--bh-font-mono);
        font-size: 13px;
        line-height: 1.5;
      }

      .prompt-chrome {
        color: var(--bh-color-text-tertiary);
        white-space: pre;
        user-select: none;
      }

      .prompt-user {
        color: var(--bh-color-primary);
      }

      .prompt-path {
        color: var(--bh-color-success, var(--bh-color-text));
      }

      .prompt-char {
        color: var(--bh-color-primary);
        white-space: pre;
        user-select: none;
        flex-shrink: 0;
      }

      .cmd-input {
        flex: 1;
        font-family: var(--bh-font-mono);
        font-size: 13px;
        line-height: 1.5;
        color: var(--bh-color-text);
        background: transparent;
        border: none;
        outline: none;
        caret-color: var(--bh-color-primary);
        padding: 0;
        margin: 0;
      }

      .cmd-input:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }

      @media (max-width: 768px) {
        .cmd-input {
          font-size: 16px;
        }
      }
    `
];
s12([
  n5()
], r22.prototype, "prompt", 2);
s12([
  n5({ attribute: "prompt-user" })
], r22.prototype, "promptUser", 2);
s12([
  n5({ attribute: "prompt-path" })
], r22.prototype, "promptPath", 2);
s12([
  n5({ type: Boolean, reflect: true })
], r22.prototype, "disabled", 2);
s12([
  r5()
], r22.prototype, "_history", 2);
s12([
  r5()
], r22.prototype, "_historyIndex", 2);
s12([
  r5()
], r22.prototype, "_tempLine", 2);
s12([
  e6(".cmd-input")
], r22.prototype, "_input", 2);
r22 = s12([
  t3("bh-terminal-input")
], r22);

// dist/molecules/terminal-hint-bar/bh-terminal-hint-bar.js
var f17 = Object.defineProperty;
var d17 = Object.getOwnPropertyDescriptor;
var c11 = (e31, t20, a20, o20) => {
  for (var r28 = o20 > 1 ? void 0 : o20 ? d17(t20, a20) : t20, n14 = e31.length - 1, i20; n14 >= 0; n14--)
    (i20 = e31[n14]) && (r28 = (o20 ? i20(t20, a20, r28) : i20(r28)) || r28);
  return o20 && r28 && f17(t20, a20, r28), r28;
};
var s13 = class extends o5 {
  constructor() {
    super(...arguments), this.hints = [];
  }
  render() {
    return b2`
      <div class="bar" part="bar">
        ${this.hints.map(
      (e31) => b2`
            <span class="hint">
              <kbd>${e31.key}</kbd> ${e31.label}
            </span>
          `
    )}
      </div>
    `;
  }
};
s13.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }

      .bar {
        display: flex;
        align-items: center;
        height: 24px;
        padding: 0 12px;
        gap: 16px;
        background: var(--bh-color-surface-recessed);
        border-top: 1px solid var(--bh-color-border);
      }

      .hint {
        font-family: var(--bh-font-mono);
        font-size: 8px;
        letter-spacing: 1px;
        text-transform: uppercase;
        color: var(--bh-color-text-tertiary);
      }

      kbd {
        color: var(--bh-color-primary);
        font-family: inherit;
      }

      @media (hover: none) and (pointer: coarse) {
        :host {
          display: none;
        }
      }
    `
];
c11([
  n5({ attribute: false })
], s13.prototype, "hints", 2);
s13 = c11([
  t3("bh-terminal-hint-bar")
], s13);

// dist/organisms/tree/bh-tree-item.js
var g12 = Object.defineProperty;
var m14 = Object.getOwnPropertyDescriptor;
var r23 = (e31, n14, l10, i20) => {
  for (var a20 = i20 > 1 ? void 0 : i20 ? m14(n14, l10) : n14, o20 = e31.length - 1, h11; o20 >= 0; o20--)
    (h11 = e31[o20]) && (a20 = (i20 ? h11(n14, l10, a20) : h11(a20)) || a20);
  return i20 && a20 && g12(n14, l10, a20), a20;
};
var t16 = class extends o5 {
  constructor() {
    super(...arguments), this.value = "", this.label = "", this.selected = false, this.expanded = false, this.indent = 0, this.roving = false, this._hasChildren = false;
  }
  render() {
    return b2`
      <div
        class="row"
        part="row"
        role="treeitem"
        aria-level=${this.indent + 1}
        aria-expanded=${this._hasChildren ? String(this.expanded) : A}
        aria-selected=${String(this.selected)}
        tabindex=${this.selected || this.roving ? "0" : "-1"}
        style="--indent-level: ${this.indent}"
        @click=${this._handleClick}
        @keydown=${this._handleKeydown}
      >
        ${this._hasChildren ? b2`<bh-icon class="chevron" part="chevron" name="chevron-right" size="sm" aria-hidden="true"></bh-icon>` : b2`<span class="chevron-placeholder"></span>`}
        <slot name="icon"></slot>
        <span class="label" part="label">${this.label}</span>
        <span class="end"><slot name="end"></slot></span>
      </div>
      <div class="children" role="group">
        <slot name="children" @slotchange=${this._onChildrenSlotChange}></slot>
      </div>
    `;
  }
  _onChildrenSlotChange(e31) {
    const n14 = e31.target;
    this._hasChildren = n14.assignedElements().length > 0;
  }
  _handleClick() {
    this._hasChildren && (this.expanded = !this.expanded), this.dispatchEvent(
      new CustomEvent("bh-tree-item-click", {
        bubbles: true,
        composed: true,
        detail: { value: this.value, label: this.label }
      })
    );
  }
  _handleKeydown(e31) {
    e31.key === "Enter" || e31.key === " " ? (e31.preventDefault(), this._handleClick()) : e31.key === "ArrowRight" && this._hasChildren && !this.expanded ? (e31.preventDefault(), this.expanded = true) : e31.key === "ArrowLeft" && this.expanded && (e31.preventDefault(), this.expanded = false);
  }
};
t16.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }

      .row {
        display: flex;
        align-items: center;
        gap: var(--bh-spacing-2);
        width: 100%;
        padding: var(--bh-spacing-1) var(--bh-spacing-2);
        padding-left: calc(var(--bh-spacing-4) + var(--indent-level) * var(--bh-spacing-4));
        border: none;
        border-left: var(--bh-border-2) solid transparent;
        border-radius: 0;
        background: none;
        color: var(--bh-color-text);
        font-family: var(--bh-font-sans);
        font-size: var(--bh-text-sm);
        line-height: var(--bh-leading-normal);
        text-align: left;
        cursor: pointer;
        transition: background var(--bh-transition-fast),
                    color var(--bh-transition-fast);
      }

      .row:hover {
        background: var(--bh-tree-item-hover-bg, var(--bh-color-secondary));
      }

      .row:focus-visible {
        outline: var(--bh-border-2) solid var(--bh-color-ring);
        outline-offset: -2px;
      }

      :host([selected]) .row {
        background: var(--bh-tree-item-selected-bg, var(--bh-color-surface-raised));
        color: var(--bh-tree-item-selected-color, var(--bh-color-primary));
        border-left-color: var(--bh-color-primary);
      }

      .chevron {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: var(--bh-spacing-4);
        height: var(--bh-spacing-4);
        flex-shrink: 0;
        transition: transform var(--bh-transition-fast);
      }

      :host([expanded]) .chevron {
        transform: rotate(90deg);
      }

      .chevron-placeholder {
        width: var(--bh-spacing-4);
        height: var(--bh-spacing-4);
        flex-shrink: 0;
      }

      .label {
        flex: 1;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .end {
        margin-left: auto;
        flex-shrink: 0;
      }

      .children {
        display: none;
      }

      :host([expanded]) .children {
        display: block;
      }
    `
];
r23([
  n5()
], t16.prototype, "value", 2);
r23([
  n5()
], t16.prototype, "label", 2);
r23([
  n5({ type: Boolean, reflect: true })
], t16.prototype, "selected", 2);
r23([
  n5({ type: Boolean, reflect: true })
], t16.prototype, "expanded", 2);
r23([
  n5({ type: Number })
], t16.prototype, "indent", 2);
r23([
  n5({ type: Boolean })
], t16.prototype, "roving", 2);
r23([
  r5()
], t16.prototype, "_hasChildren", 2);
t16 = r23([
  t3("bh-tree-item")
], t16);

// dist/organisms/tree/bh-tree.js
var m15 = Object.defineProperty;
var b13 = Object.getOwnPropertyDescriptor;
var a15 = (e31, t20, s16, r28) => {
  for (var l10 = r28 > 1 ? void 0 : r28 ? b13(t20, s16) : t20, o20 = e31.length - 1, i20; o20 >= 0; o20--)
    (i20 = e31[o20]) && (l10 = (r28 ? i20(t20, s16, l10) : i20(l10)) || l10);
  return r28 && l10 && m15(t20, s16, l10), l10;
};
var c12 = class extends o5 {
  constructor() {
    super(...arguments), this.selected = "", this._onItemClick = (e31) => {
      const { value: t20, label: s16 } = e31.detail;
      this.selected = t20, this.dispatchEvent(
        new CustomEvent("bh-select", {
          bubbles: true,
          composed: true,
          detail: { value: t20, label: s16 }
        })
      );
    };
  }
  connectedCallback() {
    super.connectedCallback(), this.addEventListener("bh-tree-item-click", this._onItemClick), this.setAttribute("role", "tree"), this._updateSelection();
  }
  disconnectedCallback() {
    super.disconnectedCallback(), this.removeEventListener("bh-tree-item-click", this._onItemClick);
  }
  updated(e31) {
    e31.has("selected") && this._updateSelection();
  }
  render() {
    return b2`<slot></slot>`;
  }
  _updateSelection() {
    const e31 = this.querySelectorAll("bh-tree-item");
    let t20 = false;
    e31.forEach((s16) => {
      s16.selected = s16.value === this.selected, s16.roving = false, s16.selected && (t20 = true);
    }), !t20 && e31.length > 0 && (e31[0].roving = true);
  }
};
c12.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
      }
    `
];
a15([
  n5()
], c12.prototype, "selected", 2);
c12 = a15([
  t3("bh-tree")
], c12);

// node_modules/lit-html/directives/repeat.js
var u12 = (e31, s16, t20) => {
  const r28 = /* @__PURE__ */ new Map();
  for (let l10 = s16; l10 <= t20; l10++) r28.set(e31[l10], l10);
  return r28;
};
var c13 = e9(class extends i9 {
  constructor(e31) {
    if (super(e31), e31.type !== t6.CHILD) throw Error("repeat() can only be used in text expressions");
  }
  dt(e31, s16, t20) {
    let r28;
    void 0 === t20 ? t20 = s16 : void 0 !== s16 && (r28 = s16);
    const l10 = [], o20 = [];
    let i20 = 0;
    for (const s17 of e31) l10[i20] = r28 ? r28(s17, i20) : i20, o20[i20] = t20(s17, i20), i20++;
    return { values: o20, keys: l10 };
  }
  render(e31, s16, t20) {
    return this.dt(e31, s16, t20).values;
  }
  update(s16, [t20, r28, c16]) {
    const d19 = M4(s16), { values: p9, keys: a20 } = this.dt(t20, r28, c16);
    if (!Array.isArray(d19)) return this.ut = a20, p9;
    const h11 = this.ut ??= [], v22 = [];
    let m18, y8, x4 = 0, j2 = d19.length - 1, k2 = 0, w3 = p9.length - 1;
    for (; x4 <= j2 && k2 <= w3; ) if (null === d19[x4]) x4++;
    else if (null === d19[j2]) j2--;
    else if (h11[x4] === a20[k2]) v22[k2] = u5(d19[x4], p9[k2]), x4++, k2++;
    else if (h11[j2] === a20[w3]) v22[w3] = u5(d19[j2], p9[w3]), j2--, w3--;
    else if (h11[x4] === a20[w3]) v22[w3] = u5(d19[x4], p9[w3]), v4(s16, v22[w3 + 1], d19[x4]), x4++, w3--;
    else if (h11[j2] === a20[k2]) v22[k2] = u5(d19[j2], p9[k2]), v4(s16, d19[x4], d19[j2]), j2--, k2++;
    else if (void 0 === m18 && (m18 = u12(a20, k2, w3), y8 = u12(h11, x4, j2)), m18.has(h11[x4])) if (m18.has(h11[j2])) {
      const e31 = y8.get(a20[k2]), t21 = void 0 !== e31 ? d19[e31] : null;
      if (null === t21) {
        const e32 = v4(s16, d19[x4]);
        u5(e32, p9[k2]), v22[k2] = e32;
      } else v22[k2] = u5(t21, p9[k2]), v4(s16, d19[x4], t21), d19[e31] = null;
      k2++;
    } else h3(d19[j2]), j2--;
    else h3(d19[x4]), x4++;
    for (; k2 <= w3; ) {
      const e31 = v4(s16, v22[w3 + 1]);
      u5(e31, p9[k2]), v22[k2++] = e31;
    }
    for (; x4 <= j2; ) {
      const e31 = d19[x4++];
      null !== e31 && h3(e31);
    }
    return this.ut = a20, p4(s16, v22), E;
  }
});

// dist/organisms/overlays/bh-command-palette.js
var g13 = Object.defineProperty;
var x3 = Object.getOwnPropertyDescriptor;
var l8 = (e31, t20, r28, o20) => {
  for (var s16 = o20 > 1 ? void 0 : o20 ? x3(t20, r28) : t20, a20 = e31.length - 1, n14; a20 >= 0; a20--)
    (n14 = e31[a20]) && (s16 = (o20 ? n14(t20, r28, s16) : n14(s16)) || s16);
  return o20 && s16 && g13(t20, r28, s16), s16;
};
var i16 = class extends o5 {
  constructor() {
    super(...arguments), this.open = false, this.placeholder = "Type a command...", this.items = [], this._query = "", this._selectedIndex = 0;
  }
  get _filteredItems() {
    return this._query ? this.items.map((e31) => ({
      item: e31,
      score: this._fuzzyScore(e31.label, this._query)
    })).filter((e31) => e31.score > 0).sort((e31, t20) => t20.score - e31.score).map((e31) => e31.item) : this.items;
  }
  _fuzzyScore(e31, t20) {
    const r28 = e31.toLowerCase(), o20 = t20.toLowerCase();
    let s16 = 0, a20 = 0, n14 = 0;
    for (let h11 = 0; h11 < r28.length && a20 < o20.length; h11++)
      r28[h11] === o20[a20] ? (s16 += 1 + n14, n14++, a20++) : n14 = 0;
    return a20 === o20.length ? s16 : 0;
  }
  toggle() {
    this.open ? this.close() : this.show();
  }
  show() {
    this.open = true, this._query = "", this._selectedIndex = 0, this.dispatchEvent(
      new CustomEvent("bh-open", { bubbles: true, composed: true })
    ), this.updateComplete.then(() => {
      var e31, t20;
      (t20 = (e31 = this.shadowRoot) == null ? void 0 : e31.querySelector("input")) == null || t20.focus();
    });
  }
  close() {
    this.open = false, this.dispatchEvent(
      new CustomEvent("bh-close", { bubbles: true, composed: true })
    );
  }
  _onInput(e31) {
    this._query = e31.target.value, this._selectedIndex = 0;
  }
  _onKeydown(e31) {
    const t20 = this._filteredItems;
    switch (e31.key) {
      case "ArrowDown":
        e31.preventDefault(), this._selectedIndex = Math.min(
          this._selectedIndex + 1,
          t20.length - 1
        );
        break;
      case "ArrowUp":
        e31.preventDefault(), this._selectedIndex = Math.max(this._selectedIndex - 1, 0);
        break;
      case "Enter":
        e31.preventDefault(), this._executeItem(t20[this._selectedIndex]);
        break;
      case "Escape":
        this.close();
        break;
    }
  }
  _executeItem(e31) {
    e31 && (this.close(), this.dispatchEvent(
      new CustomEvent("bh-execute", {
        bubbles: true,
        composed: true,
        detail: { id: e31.id, label: e31.label }
      })
    ));
  }
  _onItemClick(e31) {
    this._executeItem(e31);
  }
  render() {
    if (!this.open) return A;
    const e31 = this._filteredItems, t20 = e31.length > 0 ? `cp-item-${this._selectedIndex}` : void 0;
    return b2`
      <div class="backdrop" @click=${this.close}></div>
      <div class="palette" role="combobox" aria-expanded="true" aria-haspopup="listbox">
        <input
          type="text"
          .placeholder=${this.placeholder}
          .value=${this._query}
          @input=${this._onInput}
          @keydown=${this._onKeydown}
          aria-label=${this.placeholder || "Search commands"}
          aria-autocomplete="list"
          aria-controls="cp-results"
          aria-activedescendant=${t20 ?? A}
        />
        <div class="results" id="cp-results" role="listbox" aria-live="polite">
          ${e31.length === 0 ? b2`<div class="empty">No matching commands</div>` : c13(
      e31,
      (r28) => r28.id,
      (r28, o20) => b2`
                  <div
                    id="cp-item-${o20}"
                    class="item"
                    role="option"
                    aria-selected=${String(o20 === this._selectedIndex)}
                    @click=${() => this._onItemClick(r28)}
                  >
                    <span class="item-label">
                      ${r28.category ? b2`<span class="item-category">${r28.category}:</span>` : A}
                      ${r28.label}
                    </span>
                    ${r28.keybinding ? b2`<span class="item-keybinding">${r28.keybinding}</span>` : A}
                  </div>
                `
    )}
        </div>
      </div>
    `;
  }
  updated() {
    var t20;
    const e31 = (t20 = this.shadowRoot) == null ? void 0 : t20.querySelector('.item[aria-selected="true"]');
    e31 == null || e31.scrollIntoView({ block: "nearest" });
  }
};
i16.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: none;
        position: fixed;
        inset: 0;
        z-index: var(--bh-z-modal);
      }

      :host([open]) {
        display: flex;
        align-items: flex-start;
        justify-content: center;
        padding-top: 15vh;
      }

      .backdrop {
        position: fixed;
        inset: 0;
        background: var(--bh-command-palette-backdrop, var(--bh-color-overlay));
      }

      .palette {
        position: relative;
        width: var(--bh-command-palette-width, min(500px, 90vw));
        background: var(--bh-color-surface);
        border: var(--bh-border-1) solid var(--bh-color-border);
        border-radius: var(--bh-radius-lg);
        box-shadow: var(--bh-shadow-xl);
        overflow: hidden;
      }

      input {
        width: 100%;
        padding: var(--bh-spacing-2) var(--bh-spacing-3);
        background: var(--bh-color-surface-recessed);
        border: none;
        border-bottom: var(--bh-border-1) solid var(--bh-color-border);
        color: var(--bh-color-text);
        font-size: var(--bh-text-sm);
        font-family: inherit;
        outline: none;
      }

      input::placeholder {
        color: var(--bh-color-text-muted);
      }

      .results {
        max-height: var(--bh-command-palette-max-height, 300px);
        overflow-y: auto;
      }

      .item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: var(--bh-spacing-2) var(--bh-spacing-3);
        cursor: pointer;
        transition: background var(--bh-transition-fast);
      }

      .item:hover,
      .item[aria-selected='true'] {
        background: var(--bh-color-surface-raised);
      }

      .item-label {
        font-size: var(--bh-text-sm);
        color: var(--bh-color-text);
      }

      .item-category {
        font-size: var(--bh-text-xs);
        color: var(--bh-color-text-muted);
        margin-right: var(--bh-spacing-2);
      }

      .item-keybinding {
        font-family: var(--bh-font-mono);
        font-size: var(--bh-text-xs);
        color: var(--bh-color-text-muted);
        background: var(--bh-color-surface-recessed);
        padding: var(--bh-spacing-0-5) var(--bh-spacing-1-5);
        border-radius: var(--bh-radius-sm);
      }

      .empty {
        padding: var(--bh-spacing-3);
        font-size: var(--bh-text-sm);
        color: var(--bh-color-text-muted);
      }
    `
];
l8([
  n5({ type: Boolean, reflect: true })
], i16.prototype, "open", 2);
l8([
  n5({ type: String })
], i16.prototype, "placeholder", 2);
l8([
  n5({ type: Array })
], i16.prototype, "items", 2);
l8([
  r5()
], i16.prototype, "_query", 2);
l8([
  r5()
], i16.prototype, "_selectedIndex", 2);
i16 = l8([
  t3("bh-command-palette")
], i16);

// node_modules/lit-html/directives/class-map.js
var e27 = e9(class extends i9 {
  constructor(t20) {
    if (super(t20), t20.type !== t6.ATTRIBUTE || "class" !== t20.name || t20.strings?.length > 2) throw Error("`classMap()` can only be used in the `class` attribute and must be the only part in the attribute.");
  }
  render(t20) {
    return " " + Object.keys(t20).filter((s16) => t20[s16]).join(" ") + " ";
  }
  update(s16, [i20]) {
    if (void 0 === this.st) {
      this.st = /* @__PURE__ */ new Set(), void 0 !== s16.strings && (this.nt = new Set(s16.strings.join(" ").split(/\s/).filter((t20) => "" !== t20)));
      for (const t20 in i20) i20[t20] && !this.nt?.has(t20) && this.st.add(t20);
      return this.render(i20);
    }
    const r28 = s16.element.classList;
    for (const t20 of this.st) t20 in i20 || (r28.remove(t20), this.st.delete(t20));
    for (const t20 in i20) {
      const s17 = !!i20[t20];
      s17 === this.st.has(t20) || this.nt?.has(t20) || (s17 ? (r28.add(t20), this.st.add(t20)) : (r28.remove(t20), this.st.delete(t20)));
    }
    return E;
  }
});

// dist/organisms/overlays/bh-context-menu.js
var f18 = Object.defineProperty;
var _3 = Object.getOwnPropertyDescriptor;
var a16 = (e31, t20, s16, i20) => {
  for (var r28 = i20 > 1 ? void 0 : i20 ? _3(t20, s16) : t20, c16 = e31.length - 1, l10; c16 >= 0; c16--)
    (l10 = e31[c16]) && (r28 = (i20 ? l10(t20, s16, r28) : l10(r28)) || r28);
  return i20 && r28 && f18(t20, s16, r28), r28;
};
var o18 = class extends o5 {
  constructor() {
    super(...arguments), this.open = false, this.x = 0, this.y = 0, this.items = [], this._selectedIndex = -1;
  }
  get _actionableItems() {
    return this.items.filter((e31) => !e31.separator && !e31.disabled);
  }
  show(e31, t20, s16) {
    s16 && (this.items = s16), this.x = e31, this.y = t20, this.open = true, this._selectedIndex = -1;
  }
  hide() {
    this.open = false, this._selectedIndex = -1;
  }
  _onBackdropClick() {
    this.hide();
  }
  _onKeydown(e31) {
    const t20 = this._actionableItems;
    switch (e31.key) {
      case "Escape":
        this.hide();
        break;
      case "ArrowDown": {
        e31.preventDefault();
        const s16 = this._selectedIndex + 1;
        s16 < t20.length && (this._selectedIndex = s16);
        break;
      }
      case "ArrowUp": {
        e31.preventDefault();
        const s16 = this._selectedIndex - 1;
        s16 >= 0 && (this._selectedIndex = s16);
        break;
      }
      case "Enter": {
        e31.preventDefault();
        const s16 = t20[this._selectedIndex];
        s16 && this._selectItem(s16);
        break;
      }
    }
  }
  _selectItem(e31) {
    e31.disabled || (this.hide(), this.dispatchEvent(
      new CustomEvent("bh-select", {
        bubbles: true,
        composed: true,
        detail: { id: e31.id, label: e31.label }
      })
    ));
  }
  _isSelected(e31) {
    return this._actionableItems[this._selectedIndex] === e31;
  }
  render() {
    if (!this.open) return A;
    const t20 = this._actionableItems[this._selectedIndex], s16 = t20 ? `ctx-item-${this.items.indexOf(t20)}` : void 0;
    return b2`
      <div class="backdrop" @click=${this._onBackdropClick}></div>
      <div
        class="menu"
        role="menu"
        tabindex="-1"
        aria-activedescendant=${s16 ?? A}
        style="left: ${this.x}px; top: ${this.y}px"
        @keydown=${this._onKeydown}
      >
        ${c13(
      this.items,
      (i20) => i20.id,
      (i20, r28) => i20.separator ? b2`<div class="separator" role="separator"></div>` : b2`
                  <div
                    id="ctx-item-${r28}"
                    class=${e27({
        item: true,
        disabled: !!i20.disabled
      })}
                    role="menuitem"
                    aria-disabled=${i20.disabled ? "true" : "false"}
                    aria-selected=${String(this._isSelected(i20))}
                    @click=${() => this._selectItem(i20)}
                  >
                    ${i20.icon ? b2`<bh-icon name=${i20.icon} size="sm" aria-hidden="true"></bh-icon>` : A}
                    ${i20.label}
                  </div>
                `
    )}
      </div>
    `;
  }
  updated() {
    var e31;
    if (this.open) {
      const t20 = (e31 = this.shadowRoot) == null ? void 0 : e31.querySelector(".menu");
      t20 == null || t20.focus();
    }
  }
};
o18.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: none;
        position: fixed;
        inset: 0;
        z-index: var(--bh-z-popover);
      }

      :host([open]) {
        display: block;
      }

      .backdrop {
        position: fixed;
        inset: 0;
      }

      .menu {
        position: fixed;
        min-width: var(--bh-context-menu-min-width, 160px);
        background: var(--bh-color-surface-raised);
        border: var(--bh-border-1) solid var(--bh-color-border);
        border-radius: var(--bh-radius-md);
        box-shadow: var(--bh-shadow-md);
        padding: var(--bh-spacing-1) 0;
        overflow: hidden;
      }

      .item {
        display: flex;
        align-items: center;
        gap: var(--bh-spacing-2);
        padding: var(--bh-spacing-1-5) var(--bh-spacing-3);
        cursor: pointer;
        font-size: var(--bh-text-sm);
        color: var(--bh-color-text);
        transition: background var(--bh-transition-fast);
      }

      .item:hover,
      .item[aria-selected='true'] {
        background: var(--bh-color-surface-overlay);
      }

      .item.disabled {
        color: var(--bh-color-text-muted);
        cursor: default;
        pointer-events: none;
      }

      .separator {
        height: 1px;
        margin: var(--bh-spacing-1) 0;
        background: var(--bh-color-border-muted);
      }
    `
];
a16([
  n5({ type: Boolean, reflect: true })
], o18.prototype, "open", 2);
a16([
  n5({ type: Number })
], o18.prototype, "x", 2);
a16([
  n5({ type: Number })
], o18.prototype, "y", 2);
a16([
  n5({ type: Array })
], o18.prototype, "items", 2);
a16([
  r5()
], o18.prototype, "_selectedIndex", 2);
o18 = a16([
  t3("bh-context-menu")
], o18);

// dist/node_modules/@lit/context/lib/context-request-event.js
var r24 = class extends Event {
  constructor(t20, e31, s16, c16) {
    super("context-request", { bubbles: true, composed: true }), this.context = t20, this.contextTarget = e31, this.callback = s16, this.subscribe = c16 ?? false;
  }
};

// dist/node_modules/@lit/context/lib/controllers/context-consumer.js
var r25 = class {
  constructor(e31, t20, h11, c16) {
    if (this.subscribe = false, this.provided = false, this.value = void 0, this.t = (s16, i20) => {
      this.unsubscribe && (this.unsubscribe !== i20 && (this.provided = false, this.unsubscribe()), this.subscribe || this.unsubscribe()), this.value = s16, this.host.requestUpdate(), this.provided && !this.subscribe || (this.provided = true, this.callback && this.callback(s16, i20)), this.unsubscribe = i20;
    }, this.host = e31, t20.context !== void 0) {
      const s16 = t20;
      this.context = s16.context, this.callback = s16.callback, this.subscribe = s16.subscribe ?? false;
    } else this.context = t20, this.callback = h11, this.subscribe = c16 ?? false;
    this.host.addController(this);
  }
  hostConnected() {
    this.dispatchRequest();
  }
  hostDisconnected() {
    this.unsubscribe && (this.unsubscribe(), this.unsubscribe = void 0);
  }
  dispatchRequest() {
    this.host.dispatchEvent(new r24(this.context, this.host, this.t, this.subscribe));
  }
};

// dist/node_modules/@lit/context/lib/decorators/consume.js
function a17({ context: e31, subscribe: s16 }) {
  return (i20, c16) => {
    typeof c16 == "object" ? c16.addInitializer((function() {
      new r25(this, { context: e31, callback: (t20) => {
        i20.set.call(this, t20);
      }, subscribe: s16 });
    })) : i20.constructor.addInitializer(((t20) => {
      new r25(t20, { context: e31, callback: (o20) => {
        t20[c16] = o20;
      }, subscribe: s16 });
    }));
  };
}

// dist/organisms/terminal/bh-terminal.js
var y6 = Object.defineProperty;
var g14 = Object.getOwnPropertyDescriptor;
var i17 = (e31, t20, r28, s16) => {
  for (var a20 = s16 > 1 ? void 0 : s16 ? g14(t20, r28) : t20, n14 = e31.length - 1, h11; n14 >= 0; n14--)
    (h11 = e31[n14]) && (a20 = (s16 ? h11(t20, r28, a20) : h11(a20)) || a20);
  return s16 && a20 && y6(t20, r28, a20), a20;
};
var o19 = class extends o5 {
  constructor() {
    super(...arguments), this.title = "Terminal", this.status = "", this.statusColor = "success", this.prompt = "\u25B8 ", this.promptUser = "", this.promptPath = "~", this.maxLines = 1e3, this.autoscroll = true, this.hints = [], this.scanlines = false, this._mode = "idle";
  }
  // --- TerminalAdapter implementation ---
  /** Append text to the current (last) line. Create a line if none exist. */
  write(e31) {
    if (!this._output) return;
    let t20 = this._output.querySelector(".line:last-child");
    t20 || (t20 = document.createElement("div"), t20.className = "line", this._output.appendChild(t20)), t20.innerHTML += p3(e31), this._scrollToBottom();
  }
  /** Append a complete line. Optionally tag it with an id for later replacement. */
  writeLine(e31, t20) {
    if (!this._output) return;
    const r28 = document.createElement("div");
    r28.className = "line", r28.innerHTML = p3(e31), t20 != null && t20.id && r28.setAttribute("data-line-id", t20.id), this._output.appendChild(r28), this._trimLines(), this._scrollToBottom();
  }
  /** Write a line styled as an error. */
  writeError(e31) {
    this.writeLine("{danger}" + e31 + "{/}");
  }
  /** Update a previously written line identified by id. Falls back to writeLine. */
  replaceLine(e31, t20) {
    if (!this._output) return;
    const r28 = this._output.querySelector(`[data-line-id="${e31}"]`);
    r28 ? r28.innerHTML = p3(t20) : this.writeLine(t20, { id: e31 });
  }
  /** Enter RUNNING state — disable input. */
  startCommand() {
    this._mode = "running";
  }
  /** Return to IDLE state — re-enable and focus input. */
  endCommand() {
    this._mode = "idle", this.updateComplete.then(() => {
      var e31;
      (e31 = this._input) == null || e31.focus();
    });
  }
  /** Clear the scrollback buffer. */
  clear() {
    this._output && (this._output.innerHTML = "");
  }
  /** Focus the terminal input. */
  focus() {
    var e31;
    (e31 = this._input) == null || e31.focus();
  }
  // --- Private helpers ---
  _scrollToBottom() {
    this.autoscroll && this._output && requestAnimationFrame(() => {
      this._output.scrollTop = this._output.scrollHeight;
    });
  }
  _trimLines() {
    if (this._output && this.maxLines > 0)
      for (; this._output.children.length > this.maxLines; )
        this._output.removeChild(this._output.firstChild);
  }
  /** Echo the user's command to the output area with prompt decoration. */
  _echo(e31) {
    if (this._output) {
      if (this.promptUser) {
        const t20 = document.createElement("div");
        t20.className = "line", t20.innerHTML = '<span class="bh-t-tertiary">\u250C\u2500[</span><span class="bh-t-primary">' + this.promptUser + '</span><span class="bh-t-tertiary">]\u2500[</span><span class="bh-t-success">' + this.promptPath + '</span><span class="bh-t-tertiary">]</span>', this._output.appendChild(t20);
        const r28 = document.createElement("div");
        r28.className = "line", r28.innerHTML = '<span class="bh-t-tertiary">\u2514\u2500</span><span class="bh-t-primary">' + this.prompt + "</span>" + p3(e31), this._output.appendChild(r28);
      } else {
        const t20 = document.createElement("div");
        t20.className = "line", t20.innerHTML = '<span class="bh-t-primary">' + this.prompt + "</span>" + p3(e31), this._output.appendChild(t20);
      }
      this._trimLines(), this._scrollToBottom();
    }
  }
  // --- Event handlers ---
  async _onCommand(e31) {
    const t20 = e31.detail;
    if (this._echo(t20), this._handler) {
      const r28 = t20.split(/\s+/), s16 = r28[0], a20 = r28.slice(1);
      try {
        await this._handler.execute(s16, a20, this);
      } catch (n14) {
        this.writeError(n14 instanceof Error ? n14.message : String(n14));
      }
    } else
      this.dispatchEvent(
        new CustomEvent("bh-command", {
          detail: t20,
          bubbles: true,
          composed: true
        })
      );
  }
  _onInterrupt() {
    this._mode === "running" && this.endCommand(), this.writeLine("{tertiary}^C{/}");
  }
  _onTabComplete(e31) {
    var t20, r28;
    if ((t20 = this._handler) != null && t20.complete) {
      const s16 = this._handler.complete(e31.detail);
      if (s16.length === 1) {
        const n14 = (r28 = this._input.shadowRoot) == null ? void 0 : r28.querySelector(".cmd-input");
        n14 && (n14.value = s16[0]);
      } else s16.length > 1 && this.writeLine(s16.join("  "));
    } else
      this.dispatchEvent(
        new CustomEvent("bh-tab-complete", {
          detail: e31.detail,
          bubbles: true,
          composed: true
        })
      );
  }
  render() {
    return b2`
      <div class="terminal" part="terminal">
        <bh-terminal-bar
          title=${this.title}
          status=${this.status}
          status-color=${this.statusColor}
        ></bh-terminal-bar>
        <div class="output" part="output"></div>
        <bh-terminal-input
          prompt=${this.prompt}
          prompt-user=${this.promptUser}
          prompt-path=${this.promptPath}
          ?disabled=${this._mode === "running"}
          @bh-command=${this._onCommand}
          @bh-interrupt=${this._onInterrupt}
          @bh-tab-complete=${this._onTabComplete}
          @bh-clear=${() => this.clear()}
        ></bh-terminal-input>
        ${this.hints.length ? b2`<bh-terminal-hint-bar .hints=${this.hints}></bh-terminal-hint-bar>` : ""}
      </div>
    `;
  }
};
o19.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: block;
        color-scheme: dark;
      }

      .terminal {
        display: flex;
        flex-direction: column;
        height: var(--bh-terminal-height, 100%);
        background: var(--bh-color-cod, #0d0c0a);
        border: 1px solid var(--bh-color-tundora, #2a2826);
        border-radius: var(--bh-radius-lg, 8px);
        overflow: hidden;
        color: var(--bh-color-swiss-coffee, #c8c4bc);
        font-family: var(--bh-font-mono);
      }

      .output {
        flex: 1;
        overflow-y: auto;
        overflow-x: hidden;
        padding: 12px 16px 0;
        min-height: 0;
        background: var(--bh-color-cod, #0d0c0a);
      }

      .output::-webkit-scrollbar {
        width: 6px;
      }
      .output::-webkit-scrollbar-track {
        background: var(--bh-color-cod, #0d0c0a);
      }
      .output::-webkit-scrollbar-thumb {
        background: var(--bh-color-tundora, #2a2826);
        border-radius: 3px;
      }

      .line {
        font-family: var(--bh-font-mono);
        font-size: 13px;
        line-height: 1.5;
        white-space: pre-wrap;
        word-break: break-word;
        min-height: 1.5em;
      }

      /* Scanlines overlay */
      :host([scanlines]) .terminal {
        position: relative;
      }

      :host([scanlines]) .terminal::after {
        content: '';
        position: absolute;
        inset: 0;
        background: repeating-linear-gradient(
          0deg,
          transparent,
          transparent 2px,
          rgba(0, 0, 0, 0.08) 2px,
          rgba(0, 0, 0, 0.08) 4px
        );
        pointer-events: none;
        z-index: 1;
      }

      /* Links in terminal output */
      .output a {
        color: var(--bh-color-primary);
        text-decoration: underline;
        text-underline-offset: 2px;
      }
      .output a:hover {
        color: var(--bh-color-primary-hover, var(--bh-color-primary));
      }

      /* Terminal color tag classes — map to bh-01 semantic tokens */
      .bh-t-primary {
        color: var(--bh-color-primary);
      }
      .bh-t-success {
        color: var(--bh-color-success);
      }
      .bh-t-warning {
        color: var(--bh-color-warning);
      }
      .bh-t-danger {
        color: var(--bh-color-danger);
      }
      .bh-t-text {
        color: var(--bh-color-text);
      }
      .bh-t-bright {
        color: var(--bh-color-text-bright);
      }
      .bh-t-muted {
        color: var(--bh-color-text-muted);
      }
      .bh-t-tertiary {
        color: var(--bh-color-text-tertiary);
      }
      .bh-t-bold {
        font-weight: var(--bh-font-medium, 500);
      }
    `
];
i17([
  n5()
], o19.prototype, "title", 2);
i17([
  n5()
], o19.prototype, "status", 2);
i17([
  n5({ attribute: "status-color" })
], o19.prototype, "statusColor", 2);
i17([
  n5()
], o19.prototype, "prompt", 2);
i17([
  n5({ attribute: "prompt-user" })
], o19.prototype, "promptUser", 2);
i17([
  n5({ attribute: "prompt-path" })
], o19.prototype, "promptPath", 2);
i17([
  n5({ type: Number, attribute: "max-lines" })
], o19.prototype, "maxLines", 2);
i17([
  n5({ type: Boolean })
], o19.prototype, "autoscroll", 2);
i17([
  n5({ attribute: false })
], o19.prototype, "hints", 2);
i17([
  n5({ type: Boolean, reflect: true })
], o19.prototype, "scanlines", 2);
i17([
  a17({ context: n4, subscribe: true })
], o19.prototype, "_handler", 2);
i17([
  r5()
], o19.prototype, "_mode", 2);
i17([
  e6(".output")
], o19.prototype, "_output", 2);
i17([
  e6("bh-terminal-input")
], o19.prototype, "_input", 2);
o19 = i17([
  t3("bh-terminal")
], o19);

// dist/layout/flex/stack/bh-stack.js
var b14 = Object.defineProperty;
var f19 = Object.getOwnPropertyDescriptor;
var r26 = (g15, s16, p9, e31) => {
  for (var t20 = e31 > 1 ? void 0 : e31 ? f19(s16, p9) : s16, h11 = g15.length - 1, l10; h11 >= 0; h11--)
    (l10 = g15[h11]) && (t20 = (e31 ? l10(s16, p9, t20) : l10(t20)) || t20);
  return e31 && t20 && b14(s16, p9, t20), t20;
};
var a18 = class extends o5 {
  constructor() {
    super(...arguments), this.gap = "md", this.align = "stretch", this.wrap = false;
  }
  render() {
    return b2`<slot></slot>`;
  }
};
a18.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: flex;
        flex-direction: column;
        gap: var(--bh-stack-gap, var(--bh-spacing-4));
        min-width: 0;
      }

      /* Gap */
      :host([gap='none']) {
        --bh-stack-gap: 0;
      }

      :host([gap='xs']) {
        --bh-stack-gap: var(--bh-spacing-1);
      }

      :host([gap='sm']) {
        --bh-stack-gap: var(--bh-spacing-2);
      }

      :host([gap='md']) {
        --bh-stack-gap: var(--bh-spacing-4);
      }

      :host([gap='lg']) {
        --bh-stack-gap: var(--bh-spacing-6);
      }

      :host([gap='xl']) {
        --bh-stack-gap: var(--bh-spacing-8);
      }

      :host([gap='2xl']) {
        --bh-stack-gap: var(--bh-spacing-12);
      }

      /* Align */
      :host([align='start']) {
        align-items: flex-start;
      }

      :host([align='center']) {
        align-items: center;
      }

      :host([align='end']) {
        align-items: flex-end;
      }

      :host([align='stretch']) {
        align-items: stretch;
      }

      /* Wrap */
      :host([wrap]) {
        flex-wrap: wrap;
      }
    `
];
r26([
  n5({ reflect: true })
], a18.prototype, "gap", 2);
r26([
  n5({ reflect: true })
], a18.prototype, "align", 2);
r26([
  n5({ type: Boolean, reflect: true })
], a18.prototype, "wrap", 2);
a18 = r26([
  t3("bh-stack")
], a18);

// dist/layout/flex/cluster/bh-cluster.js
var f20 = Object.defineProperty;
var y7 = Object.getOwnPropertyDescriptor;
var s14 = (i20, r28, p9, a20) => {
  for (var t20 = a20 > 1 ? void 0 : a20 ? y7(r28, p9) : r28, o20 = i20.length - 1, l10; o20 >= 0; o20--)
    (l10 = i20[o20]) && (t20 = (a20 ? l10(r28, p9, t20) : l10(t20)) || t20);
  return a20 && t20 && f20(r28, p9, t20), t20;
};
var e28 = class extends o5 {
  constructor() {
    super(...arguments), this.gap = "md", this.justify = "start", this.align = "center", this.nowrap = false;
  }
  render() {
    return b2`<slot></slot>`;
  }
};
e28.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: flex;
        flex-wrap: wrap;
        gap: var(--bh-cluster-gap, var(--bh-spacing-4));
        min-width: 0;
      }

      /* Gap */
      :host([gap='none']) {
        --bh-cluster-gap: 0;
      }

      :host([gap='xs']) {
        --bh-cluster-gap: var(--bh-spacing-1);
      }

      :host([gap='sm']) {
        --bh-cluster-gap: var(--bh-spacing-2);
      }

      :host([gap='md']) {
        --bh-cluster-gap: var(--bh-spacing-4);
      }

      :host([gap='lg']) {
        --bh-cluster-gap: var(--bh-spacing-6);
      }

      :host([gap='xl']) {
        --bh-cluster-gap: var(--bh-spacing-8);
      }

      :host([gap='2xl']) {
        --bh-cluster-gap: var(--bh-spacing-12);
      }

      /* Justify */
      :host([justify='start']) {
        justify-content: flex-start;
      }

      :host([justify='center']) {
        justify-content: center;
      }

      :host([justify='end']) {
        justify-content: flex-end;
      }

      :host([justify='between']) {
        justify-content: space-between;
      }

      :host([justify='around']) {
        justify-content: space-around;
      }

      :host([justify='evenly']) {
        justify-content: space-evenly;
      }

      /* Align */
      :host([align='start']) {
        align-items: flex-start;
      }

      :host([align='center']) {
        align-items: center;
      }

      :host([align='end']) {
        align-items: flex-end;
      }

      :host([align='stretch']) {
        align-items: stretch;
      }

      /* Nowrap */
      :host([nowrap]) {
        flex-wrap: nowrap;
      }
    `
];
s14([
  n5({ reflect: true })
], e28.prototype, "gap", 2);
s14([
  n5({ reflect: true })
], e28.prototype, "justify", 2);
s14([
  n5({ reflect: true })
], e28.prototype, "align", 2);
s14([
  n5({ type: Boolean, reflect: true })
], e28.prototype, "nowrap", 2);
e28 = s14([
  t3("bh-cluster")
], e28);

// dist/layout/flex/repel/bh-repel.js
var b15 = Object.defineProperty;
var f21 = Object.getOwnPropertyDescriptor;
var n13 = (g15, r28, a20, s16) => {
  for (var e31 = s16 > 1 ? void 0 : s16 ? f21(r28, a20) : r28, p9 = g15.length - 1, l10; p9 >= 0; p9--)
    (l10 = g15[p9]) && (e31 = (s16 ? l10(r28, a20, e31) : l10(e31)) || e31);
  return s16 && e31 && b15(r28, a20, e31), e31;
};
var t17 = class extends o5 {
  constructor() {
    super(...arguments), this.gap = "md", this.align = "center";
  }
  render() {
    return b2`<slot></slot>`;
  }
};
t17.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: var(--bh-repel-gap, var(--bh-spacing-4));
        min-width: 0;
      }

      /* Gap */
      :host([gap='none']) {
        --bh-repel-gap: 0;
      }

      :host([gap='xs']) {
        --bh-repel-gap: var(--bh-spacing-1);
      }

      :host([gap='sm']) {
        --bh-repel-gap: var(--bh-spacing-2);
      }

      :host([gap='md']) {
        --bh-repel-gap: var(--bh-spacing-4);
      }

      :host([gap='lg']) {
        --bh-repel-gap: var(--bh-spacing-6);
      }

      :host([gap='xl']) {
        --bh-repel-gap: var(--bh-spacing-8);
      }

      :host([gap='2xl']) {
        --bh-repel-gap: var(--bh-spacing-12);
      }

      /* Align */
      :host([align='start']) {
        align-items: flex-start;
      }

      :host([align='center']) {
        align-items: center;
      }

      :host([align='end']) {
        align-items: flex-end;
      }

      :host([align='stretch']) {
        align-items: stretch;
      }
    `
];
n13([
  n5({ reflect: true })
], t17.prototype, "gap", 2);
n13([
  n5({ reflect: true })
], t17.prototype, "align", 2);
t17 = n13([
  t3("bh-repel")
], t17);

// dist/layout/flex/center/bh-center.js
var m16 = Object.defineProperty;
var b16 = Object.getOwnPropertyDescriptor;
var i18 = (r28, s16, o20, n14) => {
  for (var t20 = n14 > 1 ? void 0 : n14 ? b16(s16, o20) : s16, h11 = r28.length - 1, a20; h11 >= 0; h11--)
    (a20 = r28[h11]) && (t20 = (n14 ? a20(s16, o20, t20) : a20(t20)) || t20);
  return n14 && t20 && m16(s16, o20, t20), t20;
};
var e29 = class extends o5 {
  constructor() {
    super(...arguments), this.max = "none", this.gutters = "none", this.intrinsic = false;
  }
  willUpdate(r28) {
    r28.has("max") && this.style.setProperty("--bh-center-max", this.max);
  }
  render() {
    return b2`<slot></slot>`;
  }
};
e29.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: flex;
        flex-direction: column;
        align-items: stretch;
        max-inline-size: var(--bh-center-max, none);
        padding-inline: var(--bh-center-gutters, 0);
        margin-inline: auto;
        min-width: 0;
      }

      /* Intrinsic */
      :host([intrinsic]) {
        align-items: center;
      }

      /* Gutters */
      :host([gutters='none']) {
        --bh-center-gutters: 0;
      }

      :host([gutters='xs']) {
        --bh-center-gutters: var(--bh-spacing-1);
      }

      :host([gutters='sm']) {
        --bh-center-gutters: var(--bh-spacing-2);
      }

      :host([gutters='md']) {
        --bh-center-gutters: var(--bh-spacing-4);
      }

      :host([gutters='lg']) {
        --bh-center-gutters: var(--bh-spacing-6);
      }

      :host([gutters='xl']) {
        --bh-center-gutters: var(--bh-spacing-8);
      }

      :host([gutters='2xl']) {
        --bh-center-gutters: var(--bh-spacing-12);
      }
    `
];
i18([
  n5({ reflect: true })
], e29.prototype, "max", 2);
i18([
  n5({ reflect: true })
], e29.prototype, "gutters", 2);
i18([
  n5({ type: Boolean, reflect: true })
], e29.prototype, "intrinsic", 2);
e29 = i18([
  t3("bh-center")
], e29);

// dist/layout/flex/reel/bh-reel.js
var c14 = Object.defineProperty;
var f22 = Object.getOwnPropertyDescriptor;
var p8 = (r28, a20, l10, s16) => {
  for (var t20 = s16 > 1 ? void 0 : s16 ? f22(a20, l10) : a20, h11 = r28.length - 1, o20; h11 >= 0; h11--)
    (o20 = r28[h11]) && (t20 = (s16 ? o20(a20, l10, t20) : o20(t20)) || t20);
  return s16 && t20 && c14(a20, l10, t20), t20;
};
var e30 = class extends o5 {
  constructor() {
    super(...arguments), this.gap = "md", this.itemWidth = "auto", this.snap = false;
  }
  willUpdate(r28) {
    r28.has("itemWidth") && this.style.setProperty("--bh-reel-item-width", this.itemWidth);
  }
  render() {
    return b2`<slot></slot>`;
  }
};
e30.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: flex;
        overflow-x: auto;
        gap: var(--bh-reel-gap, var(--bh-spacing-4));
        min-width: 0;
      }

      /* Gap */
      :host([gap='none']) {
        --bh-reel-gap: 0;
      }

      :host([gap='xs']) {
        --bh-reel-gap: var(--bh-spacing-1);
      }

      :host([gap='sm']) {
        --bh-reel-gap: var(--bh-spacing-2);
      }

      :host([gap='md']) {
        --bh-reel-gap: var(--bh-spacing-4);
      }

      :host([gap='lg']) {
        --bh-reel-gap: var(--bh-spacing-6);
      }

      :host([gap='xl']) {
        --bh-reel-gap: var(--bh-spacing-8);
      }

      :host([gap='2xl']) {
        --bh-reel-gap: var(--bh-spacing-12);
      }

      /* Snap */
      :host([snap]) {
        scroll-snap-type: x mandatory;
      }

      :host([snap]) ::slotted(*) {
        scroll-snap-align: start;
      }

      /* Item width */
      ::slotted(*) {
        flex: 0 0 var(--bh-reel-item-width, auto);
      }
    `
];
p8([
  n5({ reflect: true })
], e30.prototype, "gap", 2);
p8([
  n5({ reflect: true, attribute: "item-width" })
], e30.prototype, "itemWidth", 2);
p8([
  n5({ type: Boolean, reflect: true })
], e30.prototype, "snap", 2);
e30 = p8([
  t3("bh-reel")
], e30);

// dist/layout/flex/cover/bh-cover.js
var m17 = Object.defineProperty;
var b17 = Object.getOwnPropertyDescriptor;
var i19 = (r28, o20, h11, s16) => {
  for (var e31 = s16 > 1 ? void 0 : s16 ? b17(o20, h11) : o20, a20 = r28.length - 1, p9; a20 >= 0; a20--)
    (p9 = r28[a20]) && (e31 = (s16 ? p9(o20, h11, e31) : p9(e31)) || e31);
  return s16 && e31 && m17(o20, h11, e31), e31;
};
var t18 = class extends o5 {
  constructor() {
    super(...arguments), this.gap = "md", this.minHeight = "100vh";
  }
  willUpdate(r28) {
    r28.has("minHeight") && this.style.setProperty("--bh-cover-min-height", this.minHeight);
  }
  render() {
    return b2`
      <slot></slot>
      <slot name="center"></slot>
      <slot name="bottom"></slot>
    `;
  }
};
t18.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: flex;
        flex-direction: column;
        gap: var(--bh-cover-gap, var(--bh-spacing-4));
        min-block-size: var(--bh-cover-min-height, 100vh);
        min-width: 0;
      }

      /* Gap */
      :host([gap='none']) {
        --bh-cover-gap: 0;
      }

      :host([gap='xs']) {
        --bh-cover-gap: var(--bh-spacing-1);
      }

      :host([gap='sm']) {
        --bh-cover-gap: var(--bh-spacing-2);
      }

      :host([gap='md']) {
        --bh-cover-gap: var(--bh-spacing-4);
      }

      :host([gap='lg']) {
        --bh-cover-gap: var(--bh-spacing-6);
      }

      :host([gap='xl']) {
        --bh-cover-gap: var(--bh-spacing-8);
      }

      :host([gap='2xl']) {
        --bh-cover-gap: var(--bh-spacing-12);
      }

      ::slotted([slot='center']) {
        flex-grow: 1;
      }
    `
];
i19([
  n5({ reflect: true })
], t18.prototype, "gap", 2);
i19([
  n5({ reflect: true, attribute: "min-height" })
], t18.prototype, "minHeight", 2);
t18 = i19([
  t3("bh-cover")
], t18);

// dist/layout/grid/grid/bh-grid.js
var d18 = Object.defineProperty;
var c15 = Object.getOwnPropertyDescriptor;
var h10 = (p9, a20, e31, s16) => {
  for (var r28 = s16 > 1 ? void 0 : s16 ? c15(a20, e31) : a20, g15 = p9.length - 1, i20; g15 >= 0; g15--)
    (i20 = p9[g15]) && (r28 = (s16 ? i20(a20, e31, r28) : i20(r28)) || r28);
  return s16 && r28 && d18(a20, e31, r28), r28;
};
var t19 = class extends o5 {
  constructor() {
    super(...arguments), this.gap = "md", this.min = "250px";
  }
  willUpdate(p9) {
    p9.has("min") && this.style.setProperty("--bh-grid-min", this.min);
  }
  render() {
    return b2`<slot></slot>`;
  }
};
t19.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: grid;
        grid-template-columns: repeat(
          auto-fit,
          minmax(min(100%, var(--bh-grid-min, 250px)), 1fr)
        );
        gap: var(--bh-grid-gap, var(--bh-spacing-4));
      }

      /* Gap */
      :host([gap='none']) {
        --bh-grid-gap: 0;
      }

      :host([gap='xs']) {
        --bh-grid-gap: var(--bh-spacing-1);
      }

      :host([gap='sm']) {
        --bh-grid-gap: var(--bh-spacing-2);
      }

      :host([gap='md']) {
        --bh-grid-gap: var(--bh-spacing-4);
      }

      :host([gap='lg']) {
        --bh-grid-gap: var(--bh-spacing-6);
      }

      :host([gap='xl']) {
        --bh-grid-gap: var(--bh-spacing-8);
      }

      :host([gap='2xl']) {
        --bh-grid-gap: var(--bh-spacing-12);
      }
    `
];
h10([
  n5({ reflect: true })
], t19.prototype, "gap", 2);
h10([
  n5({ reflect: true })
], t19.prototype, "min", 2);
t19 = h10([
  t3("bh-grid")
], t19);

// dist/layout/grid/split/bh-split.js
var b18 = Object.defineProperty;
var v21 = Object.getOwnPropertyDescriptor;
var l9 = (a20, p9, s16, e31) => {
  for (var t20 = e31 > 1 ? void 0 : e31 ? v21(p9, s16) : p9, o20 = a20.length - 1, i20; o20 >= 0; o20--)
    (i20 = a20[o20]) && (t20 = (e31 ? i20(p9, s16, t20) : i20(t20)) || t20);
  return e31 && t20 && b18(p9, s16, t20), t20;
};
var r27 = class extends o5 {
  constructor() {
    super(...arguments), this.gap = "md", this.ratio = "1/1";
  }
  willUpdate(a20) {
    if (a20.has("ratio")) {
      const p9 = this.ratio.split("/").map((s16) => `${s16.trim()}fr`).join(" ");
      this.style.setProperty("grid-template-columns", p9);
    }
  }
  render() {
    return b2`<slot></slot>`;
  }
};
r27.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: grid;
        gap: var(--bh-split-gap, var(--bh-spacing-4));
      }

      /* Gap */
      :host([gap='none']) {
        --bh-split-gap: 0;
      }

      :host([gap='xs']) {
        --bh-split-gap: var(--bh-spacing-1);
      }

      :host([gap='sm']) {
        --bh-split-gap: var(--bh-spacing-2);
      }

      :host([gap='md']) {
        --bh-split-gap: var(--bh-spacing-4);
      }

      :host([gap='lg']) {
        --bh-split-gap: var(--bh-spacing-6);
      }

      :host([gap='xl']) {
        --bh-split-gap: var(--bh-spacing-8);
      }

      :host([gap='2xl']) {
        --bh-split-gap: var(--bh-spacing-12);
      }
    `
];
l9([
  n5({ reflect: true })
], r27.prototype, "gap", 2);
l9([
  n5({ reflect: true })
], r27.prototype, "ratio", 2);
r27 = l9([
  t3("bh-split")
], r27);

// dist/layout/grid/switcher/bh-switcher.js
var b19 = Object.defineProperty;
var f23 = Object.getOwnPropertyDescriptor;
var a19 = (e31, r28, h11, p9) => {
  for (var t20 = p9 > 1 ? void 0 : p9 ? f23(r28, h11) : r28, i20 = e31.length - 1, o20; i20 >= 0; i20--)
    (o20 = e31[i20]) && (t20 = (p9 ? o20(r28, h11, t20) : o20(t20)) || t20);
  return p9 && t20 && b19(r28, h11, t20), t20;
};
var s15 = class extends o5 {
  constructor() {
    super(...arguments), this.gap = "md", this.threshold = "30rem", this.limit = 4;
  }
  willUpdate(e31) {
    if (e31.has("threshold") || e31.has("limit")) {
      this.style.setProperty("--bh-switcher-threshold", this.threshold);
      const r28 = `calc(100% / ${this.limit})`, h11 = "var(--bh-switcher-threshold, 30rem)";
      this.style.gridTemplateColumns = `repeat(auto-fit, minmax(min(100%, max(${h11}, ${r28})), 1fr))`;
    }
  }
  render() {
    return b2`<slot></slot>`;
  }
};
s15.styles = [
  ...[o5.styles].flat(),
  i`
      :host {
        display: grid;
        gap: var(--bh-switcher-gap, var(--bh-spacing-4));
      }

      /* Gap */
      :host([gap='none']) {
        --bh-switcher-gap: 0;
      }

      :host([gap='xs']) {
        --bh-switcher-gap: var(--bh-spacing-1);
      }

      :host([gap='sm']) {
        --bh-switcher-gap: var(--bh-spacing-2);
      }

      :host([gap='md']) {
        --bh-switcher-gap: var(--bh-spacing-4);
      }

      :host([gap='lg']) {
        --bh-switcher-gap: var(--bh-spacing-6);
      }

      :host([gap='xl']) {
        --bh-switcher-gap: var(--bh-spacing-8);
      }

      :host([gap='2xl']) {
        --bh-switcher-gap: var(--bh-spacing-12);
      }
    `
];
a19([
  n5({ reflect: true })
], s15.prototype, "gap", 2);
a19([
  n5({ reflect: true })
], s15.prototype, "threshold", 2);
a19([
  n5({ type: Number, reflect: true })
], s15.prototype, "limit", 2);
s15 = a19([
  t3("bh-switcher")
], s15);
export {
  o5 as BaseElement,
  l7 as BhAccordion,
  s11 as BhAccordionItem,
  a11 as BhActivityBar,
  e24 as BhActivityItem,
  e23 as BhAppShell,
  t4 as BhAvatar,
  a4 as BhBadge,
  t5 as BhButton,
  e19 as BhCard,
  e29 as BhCenter,
  e8 as BhCheckbox,
  r14 as BhChip,
  e28 as BhCluster,
  i16 as BhCommandPalette,
  o18 as BhContextMenu,
  t18 as BhCover,
  n12 as BhDataTable,
  a5 as BhDivider,
  t14 as BhFormField,
  t19 as BhGrid,
  e11 as BhIcon,
  e12 as BhInput,
  o9 as BhLed,
  t9 as BhLink,
  e20 as BhNavItem,
  a12 as BhPanelHeader,
  o11 as BhPixelDisplay,
  r17 as BhPixelPanel,
  r11 as BhProgress,
  e13 as BhRadio,
  e30 as BhReel,
  t17 as BhRepel,
  t15 as BhSectionHeader,
  s7 as BhSegmentDisplay,
  e14 as BhSelect,
  s10 as BhSidebarPanel,
  e15 as BhSkeleton,
  e17 as BhSlider,
  t12 as BhSpinner,
  r27 as BhSplit,
  a18 as BhStack,
  r20 as BhStatusBar,
  a7 as BhSwitch,
  s15 as BhSwitcher,
  r18 as BhTab,
  o16 as BhTabBar,
  e22 as BhTabPanel,
  e21 as BhTable,
  r19 as BhTabs,
  o19 as BhTerminal,
  e26 as BhTerminalBar,
  e18 as BhTerminalCursor,
  s13 as BhTerminalHintBar,
  r22 as BhTerminalInput,
  a8 as BhText,
  e16 as BhTextarea,
  r21 as BhToolbar,
  o10 as BhTooltip,
  c12 as BhTree,
  t16 as BhTreeItem,
  M2 as PIXEL_FONT,
  n10 as PixelDataController,
  a3 as TERMINAL_TAG_MAP,
  d10 as animatePixels,
  u3 as barToGrid,
  n4 as commandHandlerContext,
  M3 as compositeGrids,
  s5 as escapeTerminalHtml,
  l3 as linkifyUrls,
  c4 as parseColorTags,
  p3 as renderTerminalText,
  s4 as sparklineToGrid,
  T2 as textToGrid
};
/*! Bundled license information:

@lit/reactive-element/css-tag.js:
  (**
   * @license
   * Copyright 2019 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)

@lit/reactive-element/reactive-element.js:
lit-html/lit-html.js:
lit-element/lit-element.js:
@lit/reactive-element/decorators/custom-element.js:
@lit/reactive-element/decorators/property.js:
@lit/reactive-element/decorators/state.js:
@lit/reactive-element/decorators/event-options.js:
@lit/reactive-element/decorators/base.js:
@lit/reactive-element/decorators/query.js:
@lit/reactive-element/decorators/query-all.js:
@lit/reactive-element/decorators/query-async.js:
@lit/reactive-element/decorators/query-assigned-nodes.js:
lit-html/directive.js:
lit-html/directives/unsafe-html.js:
lit-html/directives/unsafe-svg.js:
lit-html/async-directive.js:
lit-html/directives/repeat.js:
  (**
   * @license
   * Copyright 2017 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)

lit-html/is-server.js:
@lit/context/lib/decorators/consume.js:
  (**
   * @license
   * Copyright 2022 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)

@lit/context/lib/create-context.js:
@lit/reactive-element/decorators/query-assigned-elements.js:
@lit/context/lib/context-request-event.js:
@lit/context/lib/controllers/context-consumer.js:
  (**
   * @license
   * Copyright 2021 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)

lit-html/directive-helpers.js:
lit-html/directives/live.js:
  (**
   * @license
   * Copyright 2020 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)

lit-html/directives/class-map.js:
  (**
   * @license
   * Copyright 2018 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)
*/
