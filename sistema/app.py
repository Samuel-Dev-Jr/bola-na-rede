"""
Bola na Rede - sistema de gestão do Centro de Cultura e Esporte.

Projeto de Extensão Curricularizada - UniFECAF
Análise e Desenvolvimento de Sistemas

O projeto começou só com futebol, em 2019, e hoje são cinco esportes no mesmo
espaço. Como futebol, vôlei e basquete têm turma masculina e feminina com dias
de treino diferentes, cada uma é uma modalidade separada: oito no total.

O sistema trabalha com PESSOA e MATRÍCULA. Uma pessoa pode estar matriculada em
várias modalidades, e mais da metade do Centro está. As rotas de dentro de uma
modalidade começam com /m/<slug>; a ficha da pessoa fica em /pessoas/<id>,
fora da modalidade, porque ela junta todas as atividades dela.

Não existe controle de mensalidade, e isso é de propósito: o projeto é um grupo
comunitário informal, sem CNPJ, e as atividades são gratuitas.

Pra rodar:
    python configurar.py   (só na primeira vez, cria o banco com as modalidades)
    python app.py      (abre em http://localhost:5000)
"""

import json
import os
from datetime import date

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

import autenticacao
import consultas
import db
import escalacao
import importar
from risco import ROTULO_RISCO

app = Flask(__name__)

# Teto do arquivo enviado na tela de Configurações. A planilha de chamada de um
# semestre inteiro dá umas centenas de KB, então 4 MB é folgado — e serve pra um
# arquivo enorme não derrubar o servidor tentando ler tudo na memória.
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024

# A chave que assina o cookie de sessão. Ela ficava fixa aqui, com um comentário
# meu dizendo que tinha que sair do código no dia que existisse login. Esse dia
# chegou: com login, chave conhecida deixa qualquer um forjar cookie de admin.
# Agora vem de BOLA_NA_REDE_CHAVE, e sem ela é sorteada a cada início — seguro,
# mas derruba as sessões quando o servidor reinicia.
#     Windows:  set BOLA_NA_REDE_CHAVE=<string longa e aleatória>
app.secret_key = autenticacao.chave_secreta()

# Campos de texto da ficha da pessoa. Uso essa lista pra montar o INSERT e o
# UPDATE sem repetir o nome de cada coluna nos dois lugares.
CAMPOS_PESSOA = [
    "nome", "responsavel_nome", "responsavel_parentesco", "responsavel_telefone",
    "emergencia_nome", "emergencia_telefone", "alergias", "condicoes",
    "medicacao_continua", "plano_saude", "observacoes_medicas",
]

# Essas rotas não leem o banco. O service worker e a página de offline precisam
# funcionar mesmo se o banco não existir.
ROTAS_SEM_BANCO = {"manifest", "serviceworker", "offline", "static"}


@app.before_request
def abrir_conexao():
    # Abro uma conexão por requisição e fecho no fim. Tentei deixar uma
    # conexão global antes e dava erro, porque o SQLite reclama quando a
    # conexão é usada por outra thread.
    if request.endpoint in ROTAS_SEM_BANCO:
        return
    if not db.banco_existe():
        abort(503, "Banco não encontrado. Rode `python configurar.py` antes de iniciar.")
    g.conexao = db.conectar()

    # A ordem aqui importa: primeiro descubro quem está pedindo, depois decido
    # se pode. A verificação é central e não por decorador em cada rota — com
    # 22 rotas, decorador é fácil de esquecer numa rota nova, e esquecer
    # significaria deixar aberto. Aqui o padrão é negar.
    autenticacao.carregar_usuario(g.conexao)
    return autenticacao.exigir_login()


@app.teardown_request
def fechar_conexao(_excecao=None):
    conexao = g.pop("conexao", None)
    if conexao is not None:
        conexao.close()


def carregar_modalidade(slug: str) -> dict:
    """Busca a modalidade pelo slug da URL, ou devolve 404."""
    modalidade = consultas.obter_modalidade(g.conexao, slug)
    if modalidade is None:
        abort(404)
    return modalidade


@app.template_filter("data_br")
def data_br(valor) -> str:
    if valor is None:
        return "—"
    if isinstance(valor, str):
        valor = date.fromisoformat(valor)
    return valor.strftime("%d/%m/%Y")


@app.template_filter("dia_semana")
def dia_semana(valor: date) -> str:
    return ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"][
        valor.weekday()
    ]


@app.context_processor
def variaveis_globais():
    return {
        "ROTULO_RISCO": ROTULO_RISCO,
        "hoje": consultas.hoje(),
        # Os templates precisam saber quem está logado pra decidir o que mostrar
        # no menu. Deixo disponível em toda página em vez de passar em cada
        # render_template, senão eu esqueceria em alguma e o menu ficaria errado.
        "usuario": autenticacao.usuario_atual(),
        "e_admin": autenticacao.e_admin(),
    }


# --------------------------------------------------------------------- PWA


@app.route("/manifest.webmanifest")
def manifest():
    """
    Arquivo que transforma o site em app instalável.

    É ele que diz pro celular qual é o nome, o ícone e a cor do app, e o
    "standalone" é o que faz abrir sem a barra de endereço do navegador.
    """
    return app.response_class(
        json.dumps(
            {
                "name": "Bola na Rede",
                "short_name": "Bola na Rede",
                "description": "Gestão das atividades do Centro de Cultura e "
                               "Esporte do Jardim Elizabete.",
                "start_url": "/",
                "scope": "/",
                "display": "standalone",
                "orientation": "portrait",
                "background_color": "#f5f6f4",
                "theme_color": "#0f7a3d",
                "lang": "pt-BR",
                "icons": [
                    {"src": "/static/icone-192.png", "sizes": "192x192", "type": "image/png"},
                    {"src": "/static/icone-512.png", "sizes": "512x512", "type": "image/png"},
                    {"src": "/static/icone-512.png", "sizes": "512x512",
                     "type": "image/png", "purpose": "maskable"},
                ],
                "shortcuts": [
                    {"name": "Fazer chamada", "url": "/m/futebol-masculino/chamada"},
                    {"name": "Quem está sumindo", "url": "/m/futebol-masculino/alunos?nivel=evadido"},
                    {"name": "Buscar pessoa", "url": "/pessoas"},
                ],
            },
            ensure_ascii=False,
        ),
        mimetype="application/manifest+json",
    )


@app.route("/sw.js")
def serviceworker():
    """
    O service worker precisa ser servido da raiz do site, senão ele só
    consegue controlar as páginas de dentro de /static e o app não abre
    offline.
    """
    resposta = send_from_directory(app.static_folder, "sw.js")
    resposta.headers["Content-Type"] = "text/javascript"
    resposta.headers["Service-Worker-Allowed"] = "/"
    resposta.headers["Cache-Control"] = "no-cache"
    return resposta


@app.route("/offline")
def offline():
    return render_template("offline.html")


# ------------------------------------------------------- painel do Centro


@app.route("/")
def centro():
    """Tela inicial: um cartão por modalidade."""
    return render_template("centro.html", painel=consultas.painel_do_centro(g.conexao))


@app.route("/m/<slug>")
def painel(slug: str):
    modalidade = carregar_modalidade(slug)
    return render_template(
        "painel.html",
        modalidade=modalidade,
        resumo=consultas.resumo(g.conexao, modalidade["id"]),
        frequencia_mensal=consultas.frequencia_mensal(g.conexao, modalidade["id"]),
        frequencia_turma=consultas.frequencia_por_turma(g.conexao, modalidade["id"]),
        contatos=consultas.lista_de_contato(g.conexao, modalidade["id"]),
    )


# ---------------------------------------------------- alunos da modalidade


@app.route("/m/<slug>/alunos")
def alunos(slug: str):
    modalidade = carregar_modalidade(slug)
    return render_template(
        "alunos.html",
        modalidade=modalidade,
        turmas=consultas.turmas_da_modalidade(g.conexao, modalidade["id"]),
        matriculas=consultas.listar_matriculas(
            g.conexao,
            modalidade_id=modalidade["id"],
            busca=request.args.get("busca", "").strip(),
            turma_id=request.args.get("turma", ""),
            nivel=request.args.get("nivel", ""),
        ),
        busca=request.args.get("busca", ""),
        turma_id=request.args.get("turma", ""),
        nivel=request.args.get("nivel", ""),
    )


@app.route("/m/<slug>/matricular", methods=["GET", "POST"])
def matricular(slug: str):
    """
    Matricula alguém que já está cadastrado no Centro nesta modalidade.

    É a tela que só faz sentido depois de separar pessoa de matrícula: em vez
    de cadastrar o mesmo menino de novo, eu procuro ele e adiciono a atividade.
    """
    modalidade = carregar_modalidade(slug)

    if request.method == "POST":
        pessoa_id = int(request.form["pessoa_id"])
        turma_id = int(request.form["turma_id"])
        ja_existe = g.conexao.execute(
            "SELECT 1 FROM matricula WHERE pessoa_id = ? AND turma_id = ?",
            (pessoa_id, turma_id),
        ).fetchone()
        if ja_existe:
            flash("Essa pessoa já está matriculada nessa turma.", "erro")
            return redirect(url_for("matricular", slug=slug))

        numero, erro_numero = _numero_de_camisa(turma_id)
        if erro_numero:
            flash(erro_numero, "erro")
            return redirect(url_for("matricular", slug=slug))

        g.conexao.execute(
            """
            INSERT INTO matricula (pessoa_id, turma_id, data_matricula, status, numero)
            VALUES (?,?,?, 'ativa', ?)
            """,
            (pessoa_id, turma_id,
             _data_do_form("data_matricula") or consultas.hoje(), numero),
        )
        g.conexao.commit()
        flash(f"Matrícula criada em {modalidade['nome_exibicao']}.", "sucesso")
        return redirect(url_for("pessoa_detalhe", pessoa_id=pessoa_id))

    # Só ofereço quem ainda não está nesta modalidade.
    ja_matriculados = {
        linha["pessoa_id"] for linha in g.conexao.execute(
            """
            SELECT ma.pessoa_id FROM matricula ma
            JOIN turma t ON t.id = ma.turma_id
            WHERE t.modalidade_id = ?
            """,
            (modalidade["id"],),
        )
    }
    disponiveis = [p for p in consultas.listar_pessoas(g.conexao)
                   if p["id"] not in ja_matriculados]

    return render_template(
        "matricular.html",
        modalidade=modalidade,
        turmas=consultas.turmas_da_modalidade(g.conexao, modalidade["id"]),
        pessoas=disponiveis,
    )


@app.route("/matriculas/<int:matricula_id>/encerrar", methods=["POST"])
def matricula_encerrar(matricula_id: int):
    matricula = consultas.obter_matricula(g.conexao, matricula_id)
    if matricula is None:
        abort(404)
    novo = "encerrada" if matricula["matricula_status"] == "ativa" else "ativa"
    g.conexao.execute("UPDATE matricula SET status = ? WHERE id = ?", (novo, matricula_id))
    g.conexao.commit()
    flash("Matrícula encerrada." if novo == "encerrada" else "Matrícula reaberta.",
          "sucesso")
    return redirect(url_for("pessoa_detalhe", pessoa_id=matricula["pessoa_id"]))


# ------------------------------------------------------------------ pessoas


@app.route("/pessoas")
def pessoas():
    return render_template(
        "pessoas.html",
        pessoas=consultas.listar_pessoas(g.conexao, request.args.get("busca", "").strip()),
        busca=request.args.get("busca", ""),
    )


@app.route("/pessoas/<int:pessoa_id>")
def pessoa_detalhe(pessoa_id: int):
    pessoa = consultas.obter_pessoa(g.conexao, pessoa_id)
    if pessoa is None:
        abort(404)
    return render_template("pessoa.html", pessoa=pessoa)


@app.route("/pessoas/nova", methods=["GET", "POST"])
@app.route("/m/<slug>/pessoas/nova", methods=["GET", "POST"])
def pessoa_nova(slug: str = None):
    """
    Cadastra alguém que ainda não está no Centro.

    Quando vem de dentro de uma modalidade, já matriculo na turma escolhida,
    que é o caminho normal: a criança chega pelo futebol.
    """
    modalidade = carregar_modalidade(slug) if slug else None

    if request.method == "POST":
        dados = _dados_da_pessoa()
        cursor = g.conexao.execute(
            f"""
            INSERT INTO pessoa ({", ".join(dados)}, data_nascimento, autoriza_imagem)
            VALUES ({", ".join("?" * len(dados))}, ?, ?)
            """,
            [*dados.values(), _data_do_form("data_nascimento"),
             1 if request.form.get("autoriza_imagem") else 0],
        )
        g.conexao.commit()
        pessoa_id = cursor.lastrowid

        turma_id = request.form.get("turma_id")
        if turma_id:
            # Se o número estiver ocupado eu matriculo sem número e aviso, em vez
            # de recusar o cadastro inteiro: a pessoa já foi gravada, e perder o
            # cadastro por causa da camisa seria o pior dos dois resultados.
            numero, erro_numero = _numero_de_camisa(int(turma_id))
            g.conexao.execute(
                """
                INSERT INTO matricula (pessoa_id, turma_id, data_matricula, status, numero)
                VALUES (?,?,?, 'ativa', ?)
                """,
                (pessoa_id, int(turma_id),
                 _data_do_form("data_matricula") or consultas.hoje(), numero),
            )
            g.conexao.commit()
            if erro_numero:
                flash(f"{erro_numero} Matriculei sem número.", "erro")

        flash(f"{dados['nome']} cadastrado.", "sucesso")
        return redirect(url_for("pessoa_detalhe", pessoa_id=pessoa_id))

    return render_template(
        "pessoa_form.html", pessoa=None, modalidade=modalidade,
        turmas=consultas.turmas_da_modalidade(g.conexao, modalidade["id"]) if modalidade else [],
    )


@app.route("/pessoas/<int:pessoa_id>/editar", methods=["GET", "POST"])
def pessoa_editar(pessoa_id: int):
    pessoa = consultas.obter_pessoa(g.conexao, pessoa_id)
    if pessoa is None:
        abort(404)

    if request.method == "POST":
        dados = _dados_da_pessoa()
        atribuicoes = ", ".join(f"{campo} = ?" for campo in dados)
        g.conexao.execute(
            f"""
            UPDATE pessoa SET {atribuicoes}, data_nascimento = ?,
                autoriza_imagem = ?, atualizado_em = datetime('now','localtime')
            WHERE id = ?
            """,
            [*dados.values(), _data_do_form("data_nascimento"),
             1 if request.form.get("autoriza_imagem") else 0, pessoa_id],
        )
        g.conexao.commit()
        flash("Ficha atualizada.", "sucesso")
        return redirect(url_for("pessoa_detalhe", pessoa_id=pessoa_id))

    return render_template("pessoa_form.html", pessoa=pessoa, modalidade=None, turmas=[])


def _dados_da_pessoa() -> dict:
    # Campo vazio eu gravo como None e não como string vazia, senão na tela
    # apareceria "Alergias:" com nada do lado em vez de "Nenhuma".
    dados = {}
    for campo in CAMPOS_PESSOA:
        valor = request.form.get(campo, "").strip()
        dados[campo] = valor or None
    dados["nome"] = dados["nome"] or "Sem nome"
    return dados


def _data_do_form(campo: str):
    valor = request.form.get(campo, "").strip()
    return date.fromisoformat(valor) if valor else None


def _numero_de_camisa(turma_id: int):
    """
    Lê o número da camisa do formulário e confere se está livre na turma.

    Devolve (numero, erro). O banco já garante isso com índice único por
    (turma, numero), mas deixar o erro estourar de lá daria uma tela de exceção
    pro técnico. Pegando aqui eu consigo dizer COM QUEM o número está, que é a
    informação que ele precisa pra resolver.
    """
    bruto = request.form.get("numero", "").strip()
    if not bruto:
        return None, None

    try:
        numero = int(bruto)
    except ValueError:
        return None, f"Número da camisa inválido: {bruto}."

    if not 1 <= numero <= 99:
        return None, "O número da camisa tem que estar entre 1 e 99."

    dono = g.conexao.execute(
        """
        SELECT p.nome FROM matricula ma
        JOIN pessoa p ON p.id = ma.pessoa_id
        WHERE ma.turma_id = ? AND ma.numero = ?
        """,
        (turma_id, numero),
    ).fetchone()
    if dono:
        return None, f"A camisa {numero} já é de {dono['nome']} nessa turma."

    return numero, None


# ----------------------------------------------------------------- chamada


@app.route("/m/<slug>/chamada", methods=["GET", "POST"])
def chamada(slug: str):
    modalidade = carregar_modalidade(slug)
    turmas = consultas.turmas_da_modalidade(g.conexao, modalidade["id"])

    if request.method == "POST":
        dia = date.fromisoformat(request.form["data"])
        # Os rádios vêm com nome "matricula_12". Aqui eu separo o id.
        marcacoes = {
            int(chave.removeprefix("matricula_")): valor
            for chave, valor in request.form.items()
            if chave.startswith("matricula_")
        }
        total = consultas.salvar_chamada(g.conexao, dia, marcacoes)
        flash(f"Chamada de {dia.strftime('%d/%m/%Y')} salva com {total} alunos.",
              "sucesso")
        return redirect(url_for("chamada", slug=slug,
                                turma=request.form["turma_id"], data=dia.isoformat()))

    turma_id = int(request.args.get("turma") or turmas[0]["id"])
    parametro_data = request.args.get("data")
    dia = (date.fromisoformat(parametro_data) if parametro_data
           else consultas.proxima_data_de_aula(modalidade["dias_aula"]))

    return render_template(
        "chamada.html",
        modalidade=modalidade,
        turmas=turmas,
        turma_id=turma_id,
        turma_nome=next((t["nome"] for t in turmas if t["id"] == turma_id), ""),
        data=dia,
        matriculas=consultas.chamada_do_dia(g.conexao, turma_id, dia),
        datas_recentes=consultas.datas_recentes(g.conexao, modalidade["id"]),
    )


# ------------------------------------------------------------------ agenda


@app.route("/m/<slug>/agenda")
def agenda(slug: str):
    """
    Calendário do mês. Aceita ?mes=AAAA-MM pra navegar; se vier bagunçado,
    cai no mês de referência em vez de dar erro na cara do usuário.
    """
    modalidade = carregar_modalidade(slug)

    referencia = consultas.hoje()
    try:
        ano, mes = (int(p) for p in request.args.get("mes", "").split("-"))
        referencia = date(ano, mes, 1)
    except (ValueError, TypeError):
        pass

    return render_template(
        "agenda.html",
        modalidade=modalidade,
        agenda=consultas.agenda_do_mes(g.conexao, modalidade,
                                       referencia.year, referencia.month),
    )


# -------------------------------------------------------------- convocação


@app.route("/m/<slug>/convocacao")
def convocacoes(slug: str):
    modalidade = carregar_modalidade(slug)
    if not modalidade["tem_convocacao"]:
        abort(404)
    return render_template(
        "convocacoes.html", modalidade=modalidade,
        eventos=consultas.listar_eventos(g.conexao, modalidade["id"]),
    )


@app.route("/m/<slug>/convocacao/novo", methods=["GET", "POST"])
def convocacao_nova(slug: str):
    modalidade = carregar_modalidade(slug)
    if not modalidade["tem_convocacao"]:
        abort(404)

    if request.method == "POST":
        cursor = g.conexao.execute(
            """
            INSERT INTO evento (modalidade_id, turma_id, nome, adversario,
                                data, local, observacoes)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                modalidade["id"], int(request.form["turma_id"]),
                request.form["nome"].strip(),
                request.form.get("adversario", "").strip() or None,
                _data_do_form("data") or consultas.hoje(),
                request.form.get("local", "").strip()
                or "Centro de Cultura e Esporte — Jardim Elizabete",
                request.form.get("observacoes", "").strip() or None,
            ),
        )
        g.conexao.commit()
        flash("Evento criado. Agora selecione os convocados.", "sucesso")
        return redirect(url_for("convocacao_detalhe", evento_id=cursor.lastrowid))

    return render_template(
        "convocacao_form.html", modalidade=modalidade,
        turmas=consultas.turmas_da_modalidade(g.conexao, modalidade["id"]),
    )


@app.route("/convocacao/<int:evento_id>", methods=["GET", "POST"])
def convocacao_detalhe(evento_id: int):
    if request.method == "POST":
        # Ignoro o que não for número em vez de estourar. Antes era int(v) direto,
        # e um valor inesperado no formulário devolvia 500 com stack trace — o que
        # é feio em qualquer lugar e é pior agora que o sistema está na internet.
        ids = [int(v) for v in request.form.getlist("convocado") if v.isdigit()]
        consultas.salvar_convocacao(g.conexao, evento_id, ids)
        flash(f"Convocação salva com {len(ids)} alunos.", "sucesso")
        return redirect(url_for("convocacao_detalhe", evento_id=evento_id))

    evento = consultas.obter_evento(g.conexao, evento_id)
    if evento is None:
        abort(404)

    tipo_quadra, posicoes = escalacao.para_modalidade(evento["modalidade_slug"])
    return render_template(
        "convocacao_detalhe.html", evento=evento,
        modalidade=consultas.obter_modalidade(g.conexao, evento["modalidade_slug"]),
        mensagem=consultas.mensagem_whatsapp(evento),
        tipo_quadra=tipo_quadra, posicoes=posicoes,
    )


@app.route("/convocacao/<int:evento_id>/escalar", methods=["POST"])
@autenticacao.somente_admin
def convocacao_escalar(evento_id: int):
    """
    Põe alguém numa posição, ou manda pro banco.

    Uma requisição por movimento, e não um formulário gigante com o time todo:
    assim o técnico mexe numa peça de cada vez e nunca perde o que já montou se
    o celular cair no meio.
    """
    evento = consultas.obter_evento(g.conexao, evento_id)
    if evento is None:
        abort(404)

    bruto = request.form.get("matricula_id", "")
    if not bruto.isdigit():
        flash("Requisição inválida: matrícula não informada.", "erro")
        return redirect(url_for("convocacao_detalhe", evento_id=evento_id))
    matricula_id = int(bruto)
    posicao = request.form.get("posicao", "").strip() or None

    # Posição inventada não entra. Sem isso, um formulário adulterado gravaria
    # qualquer texto na coluna e o campo mostraria um buraco.
    if posicao and posicao not in escalacao.codigos_validos(evento["modalidade_slug"]):
        flash(f"Posição desconhecida: {posicao}.", "erro")
        return redirect(url_for("convocacao_detalhe", evento_id=evento_id))

    # Quem escala tem que ser da lista de elegíveis deste evento — senão daria
    # pra escalar alguém de outra modalidade mexendo no formulário.
    if matricula_id not in {e["matricula_id"] for e in evento["elegiveis"]}:
        flash("Essa pessoa não está entre os elegíveis deste jogo.", "erro")
        return redirect(url_for("convocacao_detalhe", evento_id=evento_id))

    consultas.escalar(g.conexao, evento_id, matricula_id, posicao)
    return redirect(url_for("convocacao_detalhe", evento_id=evento_id))


@app.route("/convocacao/<int:evento_id>/limpar-escalacao", methods=["POST"])
@autenticacao.somente_admin
def convocacao_limpar_escalacao(evento_id: int):
    consultas.limpar_escalacao(g.conexao, evento_id)
    flash("Escalação limpa. Todo mundo voltou pro banco.", "sucesso")
    return redirect(url_for("convocacao_detalhe", evento_id=evento_id))


# ------------------------------------------------------------------- login


@app.route("/entrar", methods=["GET", "POST"])
def login():
    """
    Entrada no sistema.

    Se ainda não existe nenhum usuário, a tela avisa como criar o primeiro. Não
    faço isso por formulário aberto de propósito: uma tela de "crie o primeiro
    admin" ficaria disponível na rede local pra quem chegasse primeiro.
    """
    if autenticacao.usuario_atual() is not None:
        return redirect(url_for("centro"))

    sem_usuarios = not autenticacao.existe_algum_usuario(g.conexao)

    if request.method == "POST" and not sem_usuarios:
        login_digitado = request.form.get("login", "").strip()
        senha = request.form.get("senha", "")

        usuario = autenticacao.buscar_por_login(g.conexao, login_digitado)

        # Uma mensagem só para usuário inexistente e senha errada. Mensagens
        # diferentes contariam a quem tenta quais logins existem.
        if usuario is None or not autenticacao.senha_confere(usuario["senha_hash"], senha):
            flash("Login ou senha não conferem.", "erro")
            return redirect(url_for("login", proximo=request.form.get("proximo", "")))

        autenticacao.entrar(g.conexao, usuario)

        # Só aceito destino interno. Sem isso, um link com ?proximo=http://...
        # transformaria o login numa porta pra redirecionar gente pra fora.
        proximo = request.form.get("proximo", "")
        if proximo.startswith("/") and not proximo.startswith("//"):
            return redirect(proximo)
        return redirect(url_for("centro") if usuario["papel"] == "admin"
                        else url_for("minha_area"))

    return render_template("login.html", sem_usuarios=sem_usuarios,
                           proximo=request.args.get("proximo", ""))


@app.route("/sair", methods=["POST"])
def logout():
    autenticacao.sair()
    flash("Você saiu do sistema.", "sucesso")
    return redirect(url_for("login"))


# --------------------------------------------------------- área do jogador


@app.route("/minha-area")
def minha_area():
    """
    O que o participante vê. Só o que é dele.

    Admin também pode abrir: é como a coordenação confere o que o jogador está
    vendo, sem precisar do login dele.
    """
    usuario = autenticacao.usuario_atual()

    if usuario["pessoa_id"] is None:
        return render_template("minha_area.html", pessoa=None, eventos=[])

    pessoa = consultas.obter_pessoa(g.conexao, usuario["pessoa_id"])
    if pessoa is None:
        return render_template("minha_area.html", pessoa=None, eventos=[])

    return render_template(
        "minha_area.html", pessoa=pessoa,
        eventos=consultas.eventos_da_pessoa(g.conexao, usuario["pessoa_id"]),
    )


# ------------------------------------------------------------- usuários


@app.route("/usuarios", methods=["GET", "POST"])
@autenticacao.somente_admin
def usuarios():
    """
    Gestão de acessos. Só admin — e o decorador é reforço, porque a guarda
    central já bloqueia tudo o que não está na lista do jogador.
    """
    if request.method == "POST":
        pessoa_id = request.form.get("pessoa_id") or None
        erro = autenticacao.criar_usuario(
            g.conexao,
            login=request.form.get("login", ""),
            senha=request.form.get("senha", ""),
            papel=request.form.get("papel", "jogador"),
            pessoa_id=int(pessoa_id) if pessoa_id else None,
        )
        flash(erro or f"Acesso {request.form.get('login')!r} criado.",
              "erro" if erro else "sucesso")
        return redirect(url_for("usuarios"))

    return render_template(
        "usuarios.html",
        usuarios=autenticacao.listar_usuarios(g.conexao),
        sem_acesso=autenticacao.pessoas_sem_usuario(g.conexao),
        criadas=None,
    )


@app.route("/usuarios/<int:usuario_id>/papel", methods=["POST"])
@autenticacao.somente_admin
def usuario_papel(usuario_id: int):
    erro = autenticacao.definir_papel(g.conexao, usuario_id,
                                      request.form.get("papel", ""))
    flash(erro or "Papel alterado.", "erro" if erro else "sucesso")
    return redirect(url_for("usuarios"))


@app.route("/usuarios/<int:usuario_id>/ativo", methods=["POST"])
@autenticacao.somente_admin
def usuario_ativo(usuario_id: int):
    ativar = request.form.get("ativo") == "1"

    # Desativar a própria conta funcionaria e te deixaria na rua no mesmo
    # instante. Barro aqui, além da trava do último admin.
    if not ativar and usuario_id == autenticacao.usuario_atual()["id"]:
        flash("Você não pode desativar a sua própria conta.", "erro")
        return redirect(url_for("usuarios"))

    erro = autenticacao.definir_ativo(g.conexao, usuario_id, ativar)
    flash(erro or ("Acesso reativado." if ativar else "Acesso desativado."),
          "erro" if erro else "sucesso")
    return redirect(url_for("usuarios"))


@app.route("/usuarios/<int:usuario_id>/senha", methods=["POST"])
@autenticacao.somente_admin
def usuario_senha(usuario_id: int):
    """
    Define nova senha para alguém.

    Não existe "ver a senha atual": o banco guarda hash, e isso é de propósito —
    nem a coordenação consegue ler a senha de ninguém.
    """
    nova = request.form.get("senha", "").strip() or autenticacao.senha_aleatoria()
    erro = autenticacao.definir_senha(g.conexao, usuario_id, nova)
    if erro:
        flash(erro, "erro")
    else:
        alvo = g.conexao.execute("SELECT login FROM usuario WHERE id = ?",
                                 (usuario_id,)).fetchone()
        flash(f"Senha de {alvo['login']} trocada para: {nova} — "
              f"anote agora, ela não aparece de novo.", "sucesso")
    return redirect(url_for("usuarios"))


@app.route("/usuarios/em-lote", methods=["POST"])
@autenticacao.somente_admin
def usuarios_em_lote():
    """
    Cria acesso de jogador para quem tem matrícula ativa e ainda não tem conta.

    Existe porque criar 62 acessos um por um na tela é trabalho que ninguém faz.
    As senhas aparecem UMA VEZ nesta resposta: o banco guarda só o hash, então
    depois de sair desta tela não há como recuperá-las — só definir novas.
    """
    criadas = []
    for pessoa in autenticacao.pessoas_sem_usuario(g.conexao):
        login = autenticacao.sugerir_login(g.conexao, pessoa["nome"])
        senha = autenticacao.senha_aleatoria()
        erro = autenticacao.criar_usuario(g.conexao, login, senha, "jogador",
                                          pessoa["id"])
        if erro is None:
            criadas.append({"nome": pessoa["nome"], "login": login, "senha": senha})

    if not criadas:
        flash("Todo mundo com matrícula ativa já tem acesso.", "sucesso")
        return redirect(url_for("usuarios"))

    # Renderizo em vez de redirecionar: as senhas só existem nesta resposta, e um
    # redirect as jogaria fora antes de você conseguir anotar.
    return render_template(
        "usuarios.html",
        usuarios=autenticacao.listar_usuarios(g.conexao),
        sem_acesso=autenticacao.pessoas_sem_usuario(g.conexao),
        criadas=criadas,
    )


# ---------------------------------------------------------- configurações


@app.route("/configuracoes", methods=["GET", "POST"])
def configuracoes():
    """
    Importação de planilha pela tela, pra não precisar de terminal.

    O arquivo enviado NÃO é gravado em disco: leio o conteúdo direto da
    requisição e passo pro importador. Não tem por que guardar uma cópia da
    planilha no servidor, e arquivo que não existe não vaza.
    """
    resultado = None

    if request.method == "POST":
        arquivo = request.files.get("planilha")
        if arquivo is None or not arquivo.filename:
            flash("Escolha um arquivo CSV antes de enviar.", "erro")
            return redirect(url_for("configuracoes"))

        if not arquivo.filename.casefold().endswith(".csv"):
            flash(f"{arquivo.filename} não é um .csv. Exporte a planilha como "
                  f"CSV e envie de novo.", "erro")
            return redirect(url_for("configuracoes"))

        texto = importar.decodificar(arquivo.read())
        if texto is None:
            flash("Não consegui ler o arquivo: a codificação não é UTF-8 nem "
                  "Windows-1252. Salve como CSV UTF-8 e tente de novo.", "erro")
            return redirect(url_for("configuracoes"))

        resultado = importar.importar_texto(g.conexao, arquivo.filename, texto)

    return render_template(
        "configuracoes.html",
        resultado=resultado,
        estado=importar.estado_do_banco(g.conexao),
    )


@app.errorhandler(413)
def arquivo_grande(_erro):
    """
    O Flask corta o upload sozinho quando passa do MAX_CONTENT_LENGTH, e a tela
    padrão dele não explica nada. Aqui pelo menos digo o limite.
    """
    limite = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    flash(f"Arquivo grande demais: o limite é {limite} MB.", "erro")
    return redirect(url_for("configuracoes"))


if __name__ == "__main__":
    # O modo debug agora é OPT-IN, e ele estava ligado por padrão. Duas razões
    # pra ter mudado, e as duas me morderam de verdade:
    #
    # 1. Segurança. O depurador do Werkzeug executa código no servidor a partir
    #    do navegador. Enquanto isso rodava só em localhost era risco teórico;
    #    aberto na rede ou hospedado, é a porta mais larga que existe.
    # 2. O recarregador cria um processo filho que sobrevive ao fechamento do
    #    terminal, segurando a porta. Cheguei a ter cinco servidores escutando a
    #    5000 ao mesmo tempo, de dias diferentes, e uma tela nova respondendo 404
    #    porque a requisição caiu num servidor velho.
    #
    # Pra desenvolver com recarga automática:  set BOLA_NA_REDE_DEBUG=1
    debug = os.environ.get("BOLA_NA_REDE_DEBUG") == "1"

    # PORT é o que a hospedagem define. HOST em 0.0.0.0 aceita conexão de outros
    # aparelhos; localhost só da própria máquina.
    porta = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "127.0.0.1" if debug else "0.0.0.0")

    app.run(debug=debug, host=host, port=porta)
