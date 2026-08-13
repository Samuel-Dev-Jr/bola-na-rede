"""
Gera as capturas de tela do sistema para o relatório e o vídeo pitch.

Salva em C:\\PROJETOS\\Faculdade\\evidencias\\telas.

Telas com barra fixa (a de salvar chamada) são capturadas só na viewport: numa
captura de página inteira a barra é pintada no meio do conteúdo e pareceria um
defeito no relatório.

Uso:  python testes/capturar_telas.py   (com o app rodando)
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

import _acesso

BASE = "http://127.0.0.1:5000"
DESTINO = Path(r"C:\PROJETOS\Faculdade\evidencias\telas")
DESTINO.mkdir(parents=True, exist_ok=True)

# (nome do arquivo, rota, captura a página inteira?)
DESKTOP = [
    ("desktop-01-centro", "/", True),
    ("desktop-02-painel", "/m/futebol-masculino", True),
    ("desktop-03-alunos", "/m/futebol-masculino/alunos", True),
    ("desktop-04-pessoa", "/pessoas/1", True),
    ("desktop-05-agenda", "/m/futebol-masculino/agenda", True),
    ("desktop-06-chamada", "/m/futebol-masculino/chamada", False),
    ("desktop-07-convocacao", "/convocacao/1", False),
    ("desktop-08-configuracoes", "/configuracoes", True),
    ("desktop-09-acessos", "/usuarios", True),
]

CELULAR = [
    ("celular-01-centro", "/", True),
    ("celular-02-painel", "/m/futebol-masculino", True),
    ("celular-03-pessoas", "/pessoas", True),
    ("celular-04-pessoa", "/pessoas/1", True),
    ("celular-05-chamada", "/m/futebol-masculino/chamada", False),
    ("celular-06-agenda", "/m/karate/agenda", True),
    ("celular-07-matricular", "/m/futebol-masculino/matricular", True),
]


def capturar(contexto, telas, senha):
    pagina = contexto.new_page()
    # Cada contexto é um navegador limpo, sem cookie: precisa entrar de novo,
    # senão os prints saem todos da tela de login.
    _acesso.entrar(pagina, BASE, senha)
    for nome, rota, inteira in telas:
        resposta = pagina.goto(BASE + rota, wait_until="networkidle")
        if resposta.status != 200:
            print(f"  PULOU {nome}: HTTP {resposta.status} em {rota}")
            continue
        pagina.screenshot(path=DESTINO / f"{nome}.png", full_page=inteira)
        print(f"  {nome}.png")


senha_teste = _acesso.preparar_admin()

with sync_playwright() as p:
    navegador = p.chromium.launch(channel="chrome")

    ctx = navegador.new_context(viewport={"width": 1440, "height": 900},
                                device_scale_factor=2)
    capturar(ctx, DESKTOP, senha_teste)
    ctx.close()

    # Celular do técnico à beira do campo.
    ctx = navegador.new_context(viewport={"width": 390, "height": 844},
                                device_scale_factor=3, is_mobile=True,
                                has_touch=True)
    capturar(ctx, CELULAR, senha_teste)
    ctx.close()

    navegador.close()

_acesso.remover_admin()

print(f"\nCapturas salvas em {DESTINO}")
