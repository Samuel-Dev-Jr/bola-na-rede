"""
Mede o contraste WCAG de TODOS os textos das telas, com o vidro aplicado.

Pega a cor que o navegador realmente pintou, compondo as camadas
semitransparentes, em vez de confiar no que está escrito no CSS.
"""

import sys

from playwright.sync_api import sync_playwright

import _acesso

BASE = "http://127.0.0.1:5000"

TELAS = [
    ("Centro", "/"),
    ("Pessoas", "/pessoas"),
    ("Ficha da pessoa", "/pessoas/1"),
    ("Editar pessoa", "/pessoas/1/editar"),
    ("Futebol Masculino", "/m/futebol-masculino"),
    ("Futebol Feminino", "/m/futebol-feminino"),
    ("Karate", "/m/karate"),
    ("Pilates", "/m/pilates"),
    ("Alunos", "/m/futebol-masculino/alunos"),
    ("Matricular", "/m/futebol-masculino/matricular"),
    ("Chamada", "/m/futebol-masculino/chamada"),
    ("Agenda", "/m/volei-feminino/agenda"),
    ("Convocacao", "/convocacao/1"),
    ("Configuracoes", "/configuracoes"),
    ("Minha area", "/minha-area"),
    ("Acessos", "/usuarios"),
]

# A tela de entrar é medida ANTES do login, que é o único momento em que ela
# aparece. Na lista de cima ela não funcionaria: o teste chegaria nela já logado
# e seria redirecionado, medindo outra tela e dizendo que mediu essa.
TELAS_SEM_LOGIN = [
    ("Entrar", "/entrar"),
]

MEDIR = r"""
() => {
  function lum(c) {
    const [r, g, b] = c.map(v => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }
  // O Chrome devolve color-mix() como "color(srgb 0.04 0.34 0.17)", com os
  // canais de 0 a 1. Sem tratar isso, o valor era lido como se fosse 0-255 e
  // todo texto virava quase preto, dando contraste falso de 1:1.
  function nums(s) {
    const m = s.match(/[\d.]+/g);
    if (!m) return null;
    const v = m.map(Number);
    if (s.startsWith('color(')) {
      const canais = v.slice(0, 3).map(x => x * 255);
      return v.length > 3 ? [...canais, v[3]] : canais;
    }
    return v;
  }
  // Compoe os fundos semitransparentes ate achar um opaco.
  function fundoReal(el) {
    const pilha = [];
    let n = el;
    while (n && n !== document.documentElement) {
      const m = nums(getComputedStyle(n).backgroundColor);
      if (m) {
        const a = m.length > 3 ? m[3] : 1;
        if (a > 0) pilha.push([m[0], m[1], m[2], a]);
        if (a === 1) break;
      }
      n = n.parentElement;
    }
    let acc = [255, 255, 255];
    for (const [r, g, b, a] of pilha.reverse()) {
      acc = [acc[0]*(1-a)+r*a, acc[1]*(1-a)+g*a, acc[2]*(1-a)+b*a];
    }
    return acc;
  }

  const problemas = [];
  const vistos = new Set();
  let pulados = 0;

  // Se algum ancestral pinta gradiente, a cor de fundo real depende de onde
  // exatamente o texto caiu. Nao da pra medir compondo camadas, entao eu pulo
  // e conto, em vez de inventar um numero errado.
  function sobreGradiente(el) {
    let n = el;
    while (n && n !== document.documentElement) {
      if (getComputedStyle(n).backgroundImage !== 'none') return true;
      n = n.parentElement;
    }
    return false;
  }

  for (const el of document.querySelectorAll('body *')) {
    // So elementos que tem texto proprio visivel.
    const texto = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join('');
    if (!texto) continue;
    const est = getComputedStyle(el);
    if (est.visibility === 'hidden' || est.display === 'none') continue;
    if (el.getBoundingClientRect().width === 0) continue;

    if (sobreGradiente(el)) { pulados++; continue; }

    const cor = nums(est.color);
    if (!cor) continue;
    const fundo = fundoReal(el);
    const l1 = lum(cor.slice(0, 3)), l2 = lum(fundo);
    const razao = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);

    const tam = parseFloat(est.fontSize);
    const negrito = parseInt(est.fontWeight, 10) >= 700;
    const grande = tam >= 24 || (tam >= 18.66 && negrito);
    const minimo = grande ? 3.0 : 4.5;

    if (razao < minimo) {
      const chave = el.className + '|' + Math.round(razao * 10);
      if (vistos.has(chave)) continue;
      vistos.add(chave);
      problemas.push({
        classe: (el.className || el.tagName).toString().slice(0, 38),
        trecho: texto.slice(0, 30),
        razao: Math.round(razao * 100) / 100,
        tam: Math.round(tam),
        minimo,
      });
    }
  }
  return {problemas, pulados};
}
"""

total = 0
senha_teste = _acesso.preparar_admin()

with sync_playwright() as p:
    navegador = p.chromium.launch(channel="chrome")
    ctx = navegador.new_context(viewport={"width": 390, "height": 844},
                                device_scale_factor=2)
    pagina = ctx.new_page()

    def medir(nome, rota):
        global total
        pagina.goto(BASE + rota, wait_until="networkidle")
        r = pagina.evaluate(MEDIR)
        problemas, pulados = r["problemas"], r["pulados"]
        if problemas:
            print(f"\n  {nome}:")
            for pb in problemas:
                total += 1
                print(f"    {pb['razao']:>5}:1 (min {pb['minimo']}) "
                      f"{pb['tam']}px .{pb['classe']} -> \"{pb['trecho']}\"")
        else:
            print(f"  [OK] {nome}  ({pulados} sobre gradiente, nao medidos)")

    for nome, rota in TELAS_SEM_LOGIN:
        medir(nome, rota)

    _acesso.entrar(pagina, BASE, senha_teste)

    for nome, rota in TELAS:
        medir(nome, rota)

    ctx.close()
    navegador.close()

_acesso.remover_admin()

print()
if total:
    print(f"{total} texto(s) abaixo do minimo WCAG AA.")
    sys.exit(1)
print("Todos os textos passam no WCAG AA.")
