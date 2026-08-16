"""Encontra quem está estourando a largura da viewport em cada tela."""

import sys

from playwright.sync_api import sync_playwright

import _acesso

BASE = "http://127.0.0.1:5000"
ROTAS = [
    "/", "/pessoas", "/pessoas/1", "/pessoas/1/editar", "/pessoas/nova",
    "/m/futebol-masculino", "/m/futebol-feminino", "/m/bale", "/m/karate",
    "/m/futebol-masculino/alunos", "/m/futebol-masculino/matricular",
    "/m/futebol-masculino/chamada", "/m/karate/agenda",
    "/m/futebol-masculino/convocacao", "/convocacao/1",
    "/configuracoes", "/entrar", "/minha-area", "/usuarios",
]
LARGURAS = [(390, "mobile"), (768, "tablet"), (1440, "desktop")]

# Lista os elementos cuja borda direita passa da largura do documento.
CULPADOS = """
() => {
  const limite = document.documentElement.clientWidth;
  const achados = [];
  for (const el of document.querySelectorAll('*')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0) continue;
    if (r.right > limite + 1 || r.left < -1) {
      achados.push({
        tag: el.tagName.toLowerCase(),
        classe: (el.className && el.className.toString().slice(0, 46)) || '',
        esq: Math.round(r.left),
        dir: Math.round(r.right),
        larg: Math.round(r.width),
      });
    }
  }
  return {
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: limite,
    achados: achados.slice(0, 8),
  };
}
"""

# Dois contadores separados de propósito. Antes eu tinha um só, e o resumo
# dizia "N telas com estouro horizontal" mesmo quando as N eram rotas em 404 —
# o que é problema de dado faltando, não de layout. Eu mesmo me confundi lendo
# esse resumo.
estouros = 0
rotas_quebradas = 0

senha_teste = _acesso.preparar_admin()

with sync_playwright() as p:
    navegador = p.chromium.launch(channel="chrome")
    for largura, rotulo in LARGURAS:
        pagina = navegador.new_page(viewport={"width": largura, "height": 900})
        # Cada viewport é uma página nova, então cada uma precisa entrar de novo.
        _acesso.entrar(pagina, BASE, senha_teste)
        print(f"\n=== {rotulo} ({largura}px) ===")
        for rota in ROTAS:
            resp = pagina.goto(BASE + rota, wait_until="networkidle")
            if resp.status != 200:
                print(f"  ROTA QUEBRADA {rota}: HTTP {resp.status}")
                rotas_quebradas += 1
                continue
            r = pagina.evaluate(CULPADOS)
            excesso = r["scrollWidth"] - r["clientWidth"]
            if excesso > 0:
                estouros += 1
                print(f"  ESTOURO {rota}: scroll={r['scrollWidth']} client={r['clientWidth']} (+{excesso}px)")
                for a in r["achados"]:
                    print(f"      <{a['tag']} class=\"{a['classe']}\"> esq={a['esq']} dir={a['dir']} larg={a['larg']}")
            else:
                print(f"  ok      {rota}")
        pagina.close()
    navegador.close()

_acesso.remover_admin()

print("\n" + "=" * 56)
print(f"{estouros} tela(s) com estouro horizontal." if estouros
      else "Nenhum estouro horizontal.")
if rotas_quebradas:
    print(f"{rotas_quebradas} rota(s) sem responder 200 — isso é dado faltando "
          f"no banco, não problema de layout.")
sys.exit(1 if estouros or rotas_quebradas else 0)
