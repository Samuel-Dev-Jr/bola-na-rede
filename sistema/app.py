"""
Centro de Cultura e Esportes - sistema de gestão das atividades do Centro.

Projeto de Extensão Curricularizada - UniFECAF
Análise e Desenvolvimento de Sistemas

O projeto começou só com futebol de campo, em 2019, e hoje o Centro oferece
futsal, jiu-jitsu, balé e dança, boa parte em parceria com a ONG ABOA. No
sistema entraram três: futsal masculino, futsal feminino e jiu-jitsu. Balé e
dança ficaram de fora a pedido deles, porque naquelas turmas o contato com as
famílias já acontece pelo grupo de WhatsApp.

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

# A chave que assina o cookie de sessão vem de CENTRO_CHAVE; sem ela é sorteada
# a cada início, o que derruba as sessões no reinício.
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

# Tabela nova entra por migração, uma vez por processo. Aditivo, não apaga nada.
if db.banco_existe():
    db.aplicar_migracoes()


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


# Numeração do Python: 0 = segunda. É a mesma do modalidade.dias_aula.
DIAS_DA_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta",
                  "Sábado", "Domingo"]


@app.template_filter("dia_semana")
def dia_semana(valor: date) -> str:
    return DIAS_DA_SEMANA[valor.weekday()]


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
                "name": "Centro de Cultura e Esportes",
                # O celular corta o rótulo do ícone em ~12 caracteres.
                "short_name": "Centro CE",
                "description": "Gestão das atividades do Centro de Cultura e "
                               "Esportes do Jardim Elizabete.",
                "start_url": "/",
                "scope": "/",
                "display": "standalone",
                "orientation": "portrait",
                "background_color": "#f5f6f4",
                "theme_color": "#0f7a3d",
                "lang": "pt-BR",
                # O maskable é arquivo separado: o Android recorta esse ícone
                # e só garante os 80% centrais — com a logo inteira o corte
                # comia o "JARDIM ELIZABETE".
                "icons": [
                    {"src": "/static/icone-192.png", "sizes": "192x192", "type": "image/png"},
                    {"src": "/static/icone-512.png", "sizes": "512x512", "type": "image/png"},
                    {"src": "/static/icone-maskable-512.png", "sizes": "512x512",
                     "type": "image/png", "purpose": "maskable"},
                ],
                "shortcuts": [
                    {"name": "Fazer chamada", "url": "/m/futsal-masculino/chamada"},
                    {"name": "Quem está sumindo", "url": "/m/futsal-masculino/alunos?nivel=evadido"},
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


@app.route("/m/<slug>/horario", methods=["GET", "POST"])
@autenticacao.somente_admin
def modalidade_horario(slug: str):
    """
    Edita os dias e o horário de uma modalidade. Antes isso vivia no
    configurar.py e mudar horário exigia recriar o banco. dias_aula é o que o
    sistema lê ("0,2,4"); horario é texto livre pra pessoa ler.
    """
    modalidade = carregar_modalidade(slug)

    if request.method == "POST":
        # getlist porque são caixas de seleção; o int() filtra qualquer coisa
        # que não seja dia da semana antes de virar texto de banco.
        dias = sorted({
            int(d) for d in request.form.getlist("dias")
            if d.isdigit() and int(d) < len(DIAS_DA_SEMANA)
        })
        horario = request.form.get("horario", "").strip()

        if not dias:
            flash("Marque pelo menos um dia da semana.", "erro")
            return redirect(url_for("modalidade_horario", slug=slug))

        if not horario:
            flash("Escreva o horário do jeito que ele deve aparecer na tela.",
                  "erro")
            return redirect(url_for("modalidade_horario", slug=slug))

        g.conexao.execute(
            "UPDATE modalidade SET dias_aula = ?, horario = ? WHERE id = ?",
            (",".join(str(d) for d in dias), horario, modalidade["id"]),
        )
        g.conexao.commit()
        flash("Horário atualizado.", "sucesso")
        return redirect(url_for("painel", slug=slug))

    return render_template(
        "modalidade_horario.html",
        modalidade=modalidade,
        dias_da_semana=list(enumerate(DIAS_DA_SEMANA)),
        dias_marcados={int(d) for d in modalidade["dias_aula"].split(",")},
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
        pessoa_id = _inteiro_do_form("pessoa_id")
        turma_id = _inteiro_do_form("turma_id")
        if pessoa_id is None or turma_id is None:
            flash("Escolha a pessoa e a turma.", "erro")
            return redirect(url_for("matricular", slug=slug))

        # A turma tem que ser desta modalidade, senão um turma_id trocado no
        # formulário matricularia a pessoa em outra atividade por esta tela.
        turma_ok = g.conexao.execute(
            "SELECT 1 FROM turma WHERE id = ? AND modalidade_id = ?",
            (turma_id, modalidade["id"]),
        ).fetchone()
        if turma_ok is None:
            flash("Essa turma não é desta modalidade.", "erro")
            return redirect(url_for("matricular", slug=slug))

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


@app.route("/matriculas/<int:matricula_id>/editar", methods=["GET", "POST"])
@autenticacao.somente_admin
def matricula_editar(matricula_id: int):
    """
    Corrige turma e camisa de quem já está matriculado. Trocar de turma não
    mexe na presença: ela aponta pra matrícula, então o histórico sobe junto.
    """
    matricula = consultas.obter_matricula(g.conexao, matricula_id)
    if matricula is None:
        abort(404)
    modalidade = carregar_modalidade(matricula["modalidade_slug"])

    if request.method == "POST":
        erro, turma_id, numero = _matricula_do_form(matricula, modalidade["id"])
        if erro:
            flash(erro, "erro")
            return redirect(url_for("matricula_editar", matricula_id=matricula_id))

        g.conexao.execute(
            "UPDATE matricula SET turma_id = ?, numero = ? WHERE id = ?",
            (turma_id, numero, matricula_id),
        )
        g.conexao.commit()
        flash("Matrícula atualizada.", "sucesso")
        return redirect(url_for("pessoa_detalhe", pessoa_id=matricula["pessoa_id"]))

    return render_template(
        "matricula_form.html",
        matricula=matricula,
        modalidade=modalidade,
        turmas=consultas.turmas_da_modalidade(g.conexao, modalidade["id"]),
    )


def _matricula_do_form(matricula: dict, modalidade_id: int):
    """
    Valida a turma e a camisa vindas do formulário de editar matrícula.

    Devolve (erro, turma_id, numero). Com erro preenchido, os outros dois não
    valem nada.
    """
    turma = g.conexao.execute(
        "SELECT id FROM turma WHERE id = ? AND modalidade_id = ?",
        (request.form.get("turma_id", "").strip(), modalidade_id),
    ).fetchone()
    if turma is None:
        return "Essa turma não é desta modalidade.", None, None
    turma_id = turma["id"]

    # O banco tem UNIQUE (pessoa_id, turma_id). Sem esta conferência, mover
    # alguém pra uma turma em que ele JÁ tem matrícula estouraria IntegrityError
    # na cara do usuário, em vez de explicar que ele já está lá.
    if turma_id != matricula["turma_id"]:
        repetida = g.conexao.execute(
            "SELECT 1 FROM matricula WHERE pessoa_id = ? AND turma_id = ? AND id != ?",
            (matricula["pessoa_id"], turma_id, matricula["matricula_id"]),
        ).fetchone()
        if repetida:
            return (f"{matricula['nome']} já tem matrícula nessa turma.", None, None)

    numero, erro_numero = _numero_de_camisa(turma_id, matricula["matricula_id"])
    if erro_numero:
        return erro_numero, None, None

    return None, turma_id, numero


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
        erro = _erro_da_ficha(dados)
        if erro:
            flash(erro, "erro")
            return redirect(request.path)

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

        turma_id = _inteiro_do_form("turma_id")
        if turma_id:
            # Se o número estiver ocupado eu matriculo sem número e aviso, em vez
            # de recusar o cadastro inteiro: a pessoa já foi gravada, e perder o
            # cadastro por causa da camisa seria o pior dos dois resultados.
            numero, erro_numero = _numero_de_camisa(turma_id)
            g.conexao.execute(
                """
                INSERT INTO matricula (pessoa_id, turma_id, data_matricula, status, numero)
                VALUES (?,?,?, 'ativa', ?)
                """,
                (pessoa_id, turma_id,
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
        erro = _erro_da_ficha(dados)
        if erro:
            flash(erro, "erro")
            return redirect(url_for("pessoa_editar", pessoa_id=pessoa_id))

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


def _inteiro_do_form(campo: str):
    """Devolve o campo como int, ou None se vier vazio ou não numérico."""
    valor = request.form.get(campo, "").strip()
    return int(valor) if valor.isdigit() else None


def _erro_da_ficha(dados: dict) -> str | None:
    """
    O que o banco recusaria com IntegrityError, eu recuso antes com mensagem.
    O formulário já tem required, mas required é do navegador — um POST montado
    à mão chega aqui sem os campos e derrubava a rota com erro 500.
    """
    obrigatorios = {
        "nome": "o nome",
        "responsavel_nome": "o nome do responsável",
        "responsavel_parentesco": "o parentesco do responsável",
        "responsavel_telefone": "o telefone do responsável",
    }
    for campo, rotulo in obrigatorios.items():
        if not dados.get(campo):
            return f"Falta {rotulo}."
    try:
        if _data_do_form("data_nascimento") is None:
            return "Falta a data de nascimento."
    except ValueError:
        return "Data de nascimento inválida."
    return None


def _numero_de_camisa(turma_id: int, ignorar_matricula_id: int | None = None):
    """
    Lê o número da camisa e confere se está livre na turma. Devolve (numero,
    erro). O banco garantiria com o índice único, mas aqui eu digo COM QUEM o
    número está. ignorar_matricula_id evita a matrícula competir consigo mesma
    na tela de edição.
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

    consulta = """
        SELECT p.nome FROM matricula ma
        JOIN pessoa p ON p.id = ma.pessoa_id
        WHERE ma.turma_id = ? AND ma.numero = ?
    """
    parametros = [turma_id, numero]
    if ignorar_matricula_id is not None:
        consulta += " AND ma.id != ?"
        parametros.append(ignorar_matricula_id)

    dono = g.conexao.execute(consulta, parametros).fetchone()
    if dono:
        return None, f"A camisa {numero} já é de {dono['nome']} nessa turma."

    return numero, None


# ----------------------------------------------------------------- chamada


@app.route("/m/<slug>/chamada", methods=["GET", "POST"])
def chamada(slug: str):
    modalidade = carregar_modalidade(slug)
    turmas = consultas.turmas_da_modalidade(g.conexao, modalidade["id"])

    if request.method == "POST":
        try:
            dia = date.fromisoformat(request.form.get("data", ""))
        except ValueError:
            flash("Data inválida.", "erro")
            return redirect(url_for("chamada", slug=slug))

        # Os rádios vêm com nome "matricula_12". Aqui eu separo o id.
        marcacoes = {
            int(chave.removeprefix("matricula_")): valor
            for chave, valor in request.form.items()
            if chave.startswith("matricula_")
            and chave.removeprefix("matricula_").isdigit()
        }
        total = consultas.salvar_chamada(g.conexao, dia, marcacoes)
        flash(f"Chamada de {dia.strftime('%d/%m/%Y')} salva com {total} alunos.",
              "sucesso")
        return redirect(url_for("chamada", slug=slug,
                                turma=request.form.get("turma_id", ""),
                                data=dia.isoformat()))

    bruto_turma = request.args.get("turma", "")
    turma_id = int(bruto_turma) if bruto_turma.isdigit() else turmas[0]["id"]
    try:
        parametro_data = request.args.get("data", "")
        dia = (date.fromisoformat(parametro_data) if parametro_data
               else consultas.proxima_data_de_aula(modalidade["dias_aula"]))
    except ValueError:
        dia = consultas.proxima_data_de_aula(modalidade["dias_aula"])

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


# ---------------------------------------------------------- plano de treino


@app.route("/m/<slug>/planos")
@autenticacao.somente_admin
def planos(slug: str):
    """Os planos de treino publicados, que aparecem na área de quem treina."""
    modalidade = carregar_modalidade(slug)
    return render_template(
        "planos.html",
        modalidade=modalidade,
        planos=consultas.planos_da_modalidade(g.conexao, modalidade["id"]),
    )


@app.route("/m/<slug>/planos/novo", methods=["GET", "POST"])
@autenticacao.somente_admin
def plano_novo(slug: str):
    modalidade = carregar_modalidade(slug)

    if request.method == "POST":
        erro = _salvar_plano(modalidade["id"])
        if erro:
            flash(erro, "erro")
            return redirect(url_for("plano_novo", slug=slug))
        flash("Plano publicado. Já aparece pra quem treina.", "sucesso")
        return redirect(url_for("planos", slug=slug))

    return render_template(
        "plano_form.html", modalidade=modalidade, plano=None,
        turmas=consultas.turmas_da_modalidade(g.conexao, modalidade["id"]),
        data_sugerida=consultas.proxima_data_de_aula(modalidade["dias_aula"]),
    )


@app.route("/planos/<int:plano_id>/editar", methods=["GET", "POST"])
@autenticacao.somente_admin
def plano_editar(plano_id: int):
    plano = consultas.obter_plano(g.conexao, plano_id)
    if plano is None:
        abort(404)
    modalidade = carregar_modalidade(plano["modalidade_slug"])

    if request.method == "POST":
        erro = _salvar_plano(modalidade["id"], plano_id=plano_id)
        if erro:
            flash(erro, "erro")
            return redirect(url_for("plano_editar", plano_id=plano_id))
        flash("Plano atualizado.", "sucesso")
        return redirect(url_for("planos", slug=modalidade["slug"]))

    return render_template(
        "plano_form.html", modalidade=modalidade, plano=plano,
        turmas=consultas.turmas_da_modalidade(g.conexao, modalidade["id"]),
        data_sugerida=plano["data"],
    )


@app.route("/planos/<int:plano_id>/excluir", methods=["POST"])
@autenticacao.somente_admin
def plano_excluir(plano_id: int):
    plano = consultas.obter_plano(g.conexao, plano_id)
    if plano is None:
        abort(404)
    g.conexao.execute("DELETE FROM plano_treino WHERE id = ?", (plano_id,))
    g.conexao.commit()
    flash("Plano removido.", "sucesso")
    return redirect(url_for("planos", slug=plano["modalidade_slug"]))


def _salvar_plano(modalidade_id: int, plano_id: int | None = None) -> str | None:
    """
    Grava o plano do formulário. Devolve mensagem de erro, ou None. Turma vazia
    vira NULL, que o planos_da_pessoa() lê como "modalidade inteira".
    """
    titulo = request.form.get("titulo", "").strip()
    conteudo = request.form.get("conteudo", "").strip()
    material = request.form.get("material", "").strip() or None
    bruto_turma = request.form.get("turma_id", "").strip()

    if not titulo:
        return "O plano precisa de um título: é o que aparece na lista."
    if not conteudo:
        return "Escreva o que vai ser feito no treino."

    try:
        data = _data_do_form("data")
    except ValueError:
        return "Data inválida."
    if data is None:
        return "Escolha a data do treino."

    turma_id = None
    if bruto_turma:
        # Confiro que a turma é DESTA modalidade. Sem isso, um turma_id trocado
        # na mão gravaria o treino do futsal dentro do jiu-jitsu, e o filtro de
        # turma da área do jogador esconderia o plano de todo mundo.
        turma_id = g.conexao.execute(
            "SELECT id FROM turma WHERE id = ? AND modalidade_id = ?",
            (bruto_turma, modalidade_id),
        ).fetchone()
        if turma_id is None:
            return "Essa turma não é desta modalidade."
        turma_id = turma_id["id"]

    if plano_id is None:
        g.conexao.execute(
            """
            INSERT INTO plano_treino (modalidade_id, turma_id, data, titulo,
                                      conteudo, material)
            VALUES (?,?,?,?,?,?)
            """,
            (modalidade_id, turma_id, data, titulo, conteudo, material),
        )
    else:
        g.conexao.execute(
            """
            UPDATE plano_treino
               SET turma_id = ?, data = ?, titulo = ?, conteudo = ?, material = ?
             WHERE id = ?
            """,
            (turma_id, data, titulo, conteudo, material, plano_id),
        )

    g.conexao.commit()
    return None


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
        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("O evento precisa de um nome.", "erro")
            return redirect(url_for("convocacao_nova", slug=slug))

        # Mesma conferência do plano de treino: turma trocada no formulário
        # criaria um jogo desta modalidade apontando pra turma de outra.
        turma_id = _inteiro_do_form("turma_id")
        if turma_id is not None:
            turma_ok = g.conexao.execute(
                "SELECT 1 FROM turma WHERE id = ? AND modalidade_id = ?",
                (turma_id, modalidade["id"]),
            ).fetchone()
            if turma_ok is None:
                flash("Essa turma não é desta modalidade.", "erro")
                return redirect(url_for("convocacao_nova", slug=slug))

        try:
            dia = _data_do_form("data") or consultas.hoje()
        except ValueError:
            flash("Data inválida.", "erro")
            return redirect(url_for("convocacao_nova", slug=slug))

        cursor = g.conexao.execute(
            """
            INSERT INTO evento (modalidade_id, turma_id, nome, adversario,
                                data, local, observacoes)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                modalidade["id"], turma_id, nome,
                request.form.get("adversario", "").strip() or None,
                dia,
                request.form.get("local", "").strip()
                or "Centro de Cultura e Esportes — Jardim Elizabete",
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
    evento = consultas.obter_evento(g.conexao, evento_id)
    if evento is None:
        abort(404)

    if request.method == "POST":
        # Só entra quem é elegível deste evento. O escalar já fazia essa
        # conferência e esta rota não — dava pra convocar alguém de outra
        # modalidade mexendo no formulário, e o irmão dela recusava.
        elegiveis = {e["matricula_id"] for e in evento["elegiveis"]}
        ids = [int(v) for v in request.form.getlist("convocado")
               if v.isdigit() and int(v) in elegiveis]
        consultas.salvar_convocacao(g.conexao, evento_id, ids)
        flash(f"Convocação salva com {len(ids)} alunos.", "sucesso")
        return redirect(url_for("convocacao_detalhe", evento_id=evento_id))

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
    Põe alguém numa posição, ou manda pro banco. Uma requisição por movimento:
    o técnico nunca perde o time montado se o celular cair no meio.
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
    Entrada no sistema. Sem nenhum usuário, a tela ensina a criar o primeiro
    pelo terminal — formulário aberto de "primeiro admin" seria de quem chegasse
    antes.
    """
    if autenticacao.usuario_atual() is not None:
        return redirect(url_for("centro"))

    sem_usuarios = not autenticacao.existe_algum_usuario(g.conexao)

    if request.method == "POST" and not sem_usuarios:
        login_digitado = request.form.get("login", "").strip()
        senha = request.form.get("senha", "")

        usuario = autenticacao.buscar_por_login(g.conexao, login_digitado)

        confere = False
        if usuario is not None:
            confere = (
                autenticacao.senha_inicial_confere(g.conexao, usuario, senha)
                if autenticacao.usa_senha_inicial(usuario)
                else autenticacao.senha_confere(usuario["senha_hash"], senha)
            )

        # Uma mensagem só para usuário inexistente e senha errada. Mensagens
        # diferentes contariam a quem tenta quais logins existem.
        if not confere:
            flash("Login ou senha não conferem.", "erro")
            return redirect(url_for("login", proximo=request.form.get("proximo", "")))

        autenticacao.entrar(g.conexao, usuario)

        if autenticacao.usa_senha_inicial(usuario):
            return redirect(url_for("senha_nova"))

        # Só aceito destino interno. Sem isso, um link com ?proximo=http://...
        # transformaria o login numa porta pra redirecionar gente pra fora.
        # A barra invertida entra na checagem porque navegador trata "/\" como
        # "//", que vira endereço de fora.
        proximo = request.form.get("proximo", "")
        if (proximo.startswith("/") and not proximo.startswith("//")
                and not proximo.startswith("/\\")):
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


@app.route("/senha-nova", methods=["GET", "POST"])
def senha_nova():
    """
    Onde quem entrou com a senha inicial define a senha própria. A guarda que
    segura a pessoa aqui até trocar está em autenticacao.exigir_login.
    """
    usuario = autenticacao.usuario_atual()

    if request.method == "POST":
        senha = request.form.get("senha", "")
        if senha != request.form.get("confirmacao", ""):
            flash("As duas senhas não são iguais.", "erro")
            return redirect(url_for("senha_nova"))

        erro = autenticacao.definir_senha(g.conexao, usuario["id"], senha)
        if erro:
            flash(erro, "erro")
            return redirect(url_for("senha_nova"))

        flash("Senha definida. É ela que vale daqui pra frente.", "sucesso")
        return redirect(url_for("centro") if usuario["papel"] == "admin"
                        else url_for("minha_area"))

    return render_template("senha_nova.html")


# --------------------------------------------------------- área do jogador


@app.route("/minha-area")
def minha_area():
    """O que o participante vê. Admin também abre, pra conferir a tela dele."""
    usuario = autenticacao.usuario_atual()

    if usuario["pessoa_id"] is None:
        return render_template("minha_area.html", pessoa=None, eventos=[], planos=[])

    pessoa = consultas.obter_pessoa(g.conexao, usuario["pessoa_id"])
    if pessoa is None:
        return render_template("minha_area.html", pessoa=None, eventos=[], planos=[])

    return render_template(
        "minha_area.html", pessoa=pessoa,
        eventos=consultas.eventos_da_pessoa(g.conexao, usuario["pessoa_id"]),
        planos=consultas.planos_da_pessoa(g.conexao, usuario["pessoa_id"]),
    )


# ------------------------------------------------------------- usuários


@app.route("/usuarios", methods=["GET", "POST"])
@autenticacao.somente_admin
def usuarios():
    """Gestão de acessos."""
    if request.method == "POST":
        erro = autenticacao.criar_usuario(
            g.conexao,
            login=request.form.get("login", ""),
            senha=request.form.get("senha", ""),
            papel=request.form.get("papel", "jogador"),
            pessoa_id=_inteiro_do_form("pessoa_id"),
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
    """Define nova senha. Não existe "ver a atual": o banco só guarda hash."""
    alvo = g.conexao.execute("SELECT login FROM usuario WHERE id = ?",
                             (usuario_id,)).fetchone()
    if alvo is None:
        abort(404)

    nova = request.form.get("senha", "").strip() or autenticacao.senha_aleatoria()
    erro = autenticacao.definir_senha(g.conexao, usuario_id, nova)
    if erro:
        flash(erro, "erro")
    else:
        flash(f"Senha de {alvo['login']} trocada para: {nova} — "
              f"anote agora, ela não aparece de novo.", "sucesso")
    return redirect(url_for("usuarios"))


@app.route("/usuarios/em-lote", methods=["POST"])
@autenticacao.somente_admin
def usuarios_em_lote():
    """
    Cria acesso de jogador pra quem tem matrícula ativa e ainda não tem conta.
    A senha inicial é a data de nascimento de cada um, trocada à força no
    primeiro acesso — sortear senha aqui gerava um hash por pessoa e o tempo
    disso derrubava a requisição em produção (ver ESPECIFICACAO.md).
    """
    criadas = []
    for pessoa in autenticacao.pessoas_sem_usuario(g.conexao):
        login = autenticacao.sugerir_login(g.conexao, pessoa["nome"])
        autenticacao.criar_acesso_inicial(g.conexao, login, pessoa["id"])
        criadas.append({"nome": pessoa["nome"], "login": login})
    g.conexao.commit()

    if not criadas:
        flash("Todo mundo com matrícula ativa já tem acesso.", "sucesso")
        return redirect(url_for("usuarios"))

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
    Importação de planilha pela tela. O arquivo não é gravado em disco: leio da
    requisição e passo pro importador — arquivo que não existe não vaza.
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
    # Debug é opt-in: o depurador do Werkzeug executa código pelo navegador, e
    # o recarregador já me deixou com cinco servidores presos na mesma porta.
    #     set CENTRO_DEBUG=1
    debug = os.environ.get("CENTRO_DEBUG") == "1"

    # PORT é o que a hospedagem define. HOST em 0.0.0.0 aceita conexão de outros
    # aparelhos; localhost só da própria máquina.
    porta = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "127.0.0.1" if debug else "0.0.0.0")

    app.run(debug=debug, host=host, port=porta)
