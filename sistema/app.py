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

# As tabelas que nasceram depois do schema original entram aqui, uma vez, no
# início do processo. É aditivo e não apaga nada — ver db.aplicar_migracoes().
# Fica fora do before_request de propósito: rodar a cada requisição seria
# desperdício, e uma vez por processo basta. Se o banco ainda não existe, o
# before_request já devolve 503 pedindo pra rodar o configurar.
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


# Os dias da semana na numeração do Python (0 = segunda), que é a mesma que o
# banco guarda em modalidade.dias_aula. Estava escrito só dentro do filtro
# abaixo; subiu pra cá quando a tela de horário passou a precisar da lista
# inteira pra montar as caixas de seleção.
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


@app.route("/m/<slug>/horario", methods=["GET", "POST"])
@autenticacao.somente_admin
def modalidade_horario(slug: str):
    """
    Edita os dias e o horário de uma modalidade pela tela.

    Isso vivia no configurar.py, em código. Trocar o horário do vôlei exigia
    editar Python e rodar o configurar de novo — e o configurar RECRIA o schema,
    ou seja, apagava o cadastro inteiro pra mudar uma linha de texto. Na prática
    o horário era imutável depois da primeira matrícula, e a coordenação
    dependia de mim pra uma coisa que muda sozinha: quadra emprestada, professor
    que troca de turno, horário de verão.

    São dois campos com papéis diferentes, e é importante não confundir:

    - `dias_aula` é máquina. Sai daqui como "0,2,4" porque é o formato que
      proxima_data_de_aula() e agenda_do_mes() já leem. Mexer nele muda a data
      que a chamada sugere e quais quadradinhos a agenda pinta como dia de aula.
    - `horario` é gente. É texto livre, escrito pra ser lido — "Seg e Qua, 18h
      às 20h" — e aparece no painel, na chamada, na agenda e na área do jogador.

    Nada disso reescreve o passado: presença já lançada continua lá igual, e o
    nível de risco sai das presenças, não daqui.
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


@app.route("/matriculas/<int:matricula_id>/editar", methods=["GET", "POST"])
@autenticacao.somente_admin
def matricula_editar(matricula_id: int):
    """
    Corrige a turma e o número da camisa de quem já está matriculado.

    Faltava, e o buraco era feio: depois de matricular, trocar a camisa ou subir
    o menino de categoria só dava pra fazer corrigindo a planilha e importando
    de novo. Menino faz aniversário e muda de categoria todo ano — isso não é
    exceção, é o funcionamento normal do Centro.

    Trocar de turma NÃO mexe na presença já registrada: presenca aponta pra
    matricula, não pra turma, então a frequência dele sobe junto com ele. Era o
    que eu queria — quem passou do Sub-13 pro Sub-15 continua sendo a mesma
    pessoa, com o mesmo histórico, e o nível de risco não zera do nada.
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

    Devolve (erro, turma_id, numero) — com erro preenchido, os outros dois não
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


def _numero_de_camisa(turma_id: int, ignorar_matricula_id: int | None = None):
    """
    Lê o número da camisa do formulário e confere se está livre na turma.

    Devolve (numero, erro). O banco já garante isso com índice único por
    (turma, numero), mas deixar o erro estourar de lá daria uma tela de exceção
    pro técnico. Pegando aqui eu consigo dizer COM QUEM o número está, que é a
    informação que ele precisa pra resolver.

    `ignorar_matricula_id` existe por causa da tela de editar matrícula: sem
    ele, abrir a matrícula do menino que é camisa 10, mudar só a turma e salvar
    devolveria "a camisa 10 já é de Fulano nessa turma" — e o Fulano seria ele
    mesmo. A matrícula que está sendo editada não pode competir consigo.
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


# ---------------------------------------------------------- plano de treino


@app.route("/m/<slug>/planos")
@autenticacao.somente_admin
def planos(slug: str):
    """
    O que vai ser feito nos treinos, publicado pelo professor.

    Era o buraco que sobrava: o sistema sabia quem estava matriculado, quem
    faltou e quem foi convocado, mas não respondia a pergunta que o atleta mais
    faz — "o que a gente vai treinar hoje?". Isso vivia no caderno do professor,
    e quem faltasse não tinha como saber o que perdeu.
    """
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
    Grava o plano vindo do formulário. Devolve a mensagem de erro, ou None.

    Criar e editar preenchem os mesmos campos com as mesmas regras, então a
    validação mora aqui em vez de duplicada nas duas rotas — foi duplicando esse
    tipo de coisa que eu já deixei o cadastro aceitar o que a edição recusava.

    A turma é opcional e vem como texto vazio quando o professor escolhe "todas
    as turmas". Gravo NULL nesse caso, que é o que planos_da_pessoa() lê como
    "vale pra modalidade inteira".
    """
    titulo = request.form.get("titulo", "").strip()
    conteudo = request.form.get("conteudo", "").strip()
    material = request.form.get("material", "").strip() or None
    bruto_turma = request.form.get("turma_id", "").strip()

    if not titulo:
        return "O plano precisa de um título — é o que aparece na lista."
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
        # na mão gravaria o treino do vôlei dentro do karatê, e o filtro de
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
