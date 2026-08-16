"""
Login, papéis e proteção das rotas.

Dois papéis: admin (a coordenação, vê tudo) e jogador (só o que é dele — nunca
ficha médica ou telefone de outra pessoa). Senha vira hash do werkzeug; o banco
nunca guarda a senha em si.
"""

import functools
import hmac
import os
import secrets
import unicodedata
from datetime import datetime, timedelta

from flask import flash, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

# Quem pode entrar sem estar logado. Só o necessário pra fazer login e pro app
# instalado não quebrar sem sessão.
ROTAS_PUBLICAS = {
    "login", "manifest", "serviceworker", "offline", "static",
}

# Rotas que um jogador pode abrir. TUDO o que não está aqui é só admin — a lista
# é de permissão, não de proibição, de propósito: se eu criar uma rota nova e
# esquecer de classificar, ela nasce fechada em vez de aberta.
ROTAS_DO_JOGADOR = {
    "minha_area", "logout", "senha_nova",
}

# A lista é curta de propósito. Cheguei a pôr `painel` aqui achando que era só
# leitura, mas ele mostra nome, risco e telefone do responsável de quem falta.
# Tela de admin não se reaproveita pro jogador só porque é leitura.

CHAVE_SESSAO = "usuario_id"
VARIAVEL_CHAVE = "CENTRO_CHAVE"

# Mínimo de caracteres na senha. Oito é pouco para a internet, mas isto roda na
# rede local do Centro e a senha vai ser digitada por criança no celular. Está
# anotado como limite conhecido na seção 4 do DECISOES.md.
MINIMO_SENHA = 8

# Depois de quantos dias sem participar o acesso de jogador é desativado.
DIAS_INATIVIDADE = 30


def chave_secreta() -> str:
    """
    A chave que assina o cookie de sessão. Vem do ambiente; sem ela, sorteio
    uma — seguro, mas derruba as sessões a cada reinício.
    """
    definida = os.environ.get(VARIAVEL_CHAVE)
    if definida:
        return definida
    return secrets.token_hex(32)


def hash_da_senha(senha: str) -> str:
    return generate_password_hash(senha)


def senha_confere(senha_hash: str, senha: str) -> bool:
    return check_password_hash(senha_hash, senha)


def usa_senha_inicial(usuario) -> bool:
    """senha_hash vazia é o marcador de conta que ainda usa a senha inicial."""
    return usuario is not None and usuario["senha_hash"] == ""


def senha_inicial_confere(conexao, usuario, senha: str) -> bool:
    """A senha inicial é a data de nascimento da pessoa: 01022014, com ou sem barras."""
    if usuario["pessoa_id"] is None:
        return False
    pessoa = conexao.execute("SELECT data_nascimento FROM pessoa WHERE id = ?",
                             (usuario["pessoa_id"],)).fetchone()
    if pessoa is None:
        return False
    esperada = pessoa["data_nascimento"].strftime("%d%m%Y")
    digitada = senha.strip().replace("/", "")
    return hmac.compare_digest(digitada, esperada)


def buscar_por_login(conexao, login: str):
    digitado = login.strip()
    usuario = conexao.execute(
        "SELECT * FROM usuario WHERE login = ? AND ativo = 1", (digitado,)
    ).fetchone()
    if usuario is not None or "@" not in digitado:
        return usuario

    # O campo também aceita o e-mail da ficha — mas só quando ele aponta pra
    # UMA pessoa: irmãos dividem o e-mail do responsável, e nesse caso cada um
    # entra pelo próprio login.
    encontrados = conexao.execute(
        """
        SELECT u.* FROM usuario u
        JOIN pessoa p ON p.id = u.pessoa_id
        WHERE p.email = ? COLLATE NOCASE AND u.ativo = 1
        """,
        (digitado,),
    ).fetchall()
    return encontrados[0] if len(encontrados) == 1 else None


def buscar_por_id(conexao, usuario_id: int):
    return conexao.execute(
        "SELECT * FROM usuario WHERE id = ? AND ativo = 1", (usuario_id,)
    ).fetchone()


def existe_algum_usuario(conexao) -> bool:
    return conexao.execute("SELECT 1 FROM usuario LIMIT 1").fetchone() is not None


def entrar(conexao, usuario) -> None:
    # Troco o identificador da sessão no login pra não permitir fixação de
    # sessão: um cookie obtido antes de entrar não vale depois.
    session.clear()
    session[CHAVE_SESSAO] = usuario["id"]
    session.permanent = False
    conexao.execute(
        "UPDATE usuario SET ultimo_acesso = ? WHERE id = ?",
        (datetime.now().isoformat(timespec="seconds"), usuario["id"]),
    )
    conexao.commit()


def sair() -> None:
    session.clear()


def usuario_atual():
    return g.get("usuario")


def e_admin() -> bool:
    usuario = usuario_atual()
    return usuario is not None and usuario["papel"] == "admin"


def carregar_usuario(conexao) -> None:
    """Põe o usuário logado em g.usuario. Chamado a cada requisição."""
    g.usuario = None
    usuario_id = session.get(CHAVE_SESSAO)
    if usuario_id is None:
        return
    usuario = buscar_por_id(conexao, usuario_id)
    if usuario is None:
        # Conta apagada ou desativada com a sessão ainda aberta.
        session.clear()
        return
    g.usuario = usuario


def rota_permitida(endpoint: str | None) -> bool:
    """
    Decide se o usuário atual pode abrir este endpoint.

    Não uso decorador em cada rota: com 22 rotas já existentes, decorador é
    fácil de esquecer numa rota nova, e esquecer significa deixar aberto. Aqui a
    verificação é central e o padrão é NEGAR.
    """
    if endpoint in ROTAS_PUBLICAS:
        return True

    usuario = usuario_atual()
    if usuario is None:
        return False

    if usuario["papel"] == "admin":
        return True

    return endpoint in ROTAS_DO_JOGADOR


def exigir_login():
    """
    Guarda de requisição. Devolve um redirect quando o acesso é negado, ou None.

    Usado no before_request, depois de carregar_usuario.
    """
    endpoint = request.endpoint

    # Quem entrou com a senha inicial (data de nascimento) primeiro define a
    # senha própria; até lá o resto do sistema não abre.
    if (usa_senha_inicial(usuario_atual()) and endpoint not in ROTAS_PUBLICAS
            and endpoint not in ("senha_nova", "logout")):
        return redirect(url_for("senha_nova"))

    if rota_permitida(endpoint):
        return None

    if usuario_atual() is None:
        # Guardo pra onde a pessoa queria ir, pra levar ela lá depois do login.
        destino = request.full_path if request.query_string else request.path
        return redirect(url_for("login", proximo=destino))

    flash("Essa parte do sistema é da coordenação.", "erro")
    return redirect(url_for("minha_area"))


# ------------------------------------------------------ gestão de usuários


def listar_usuarios(conexao) -> list[dict]:
    return [dict(l) for l in conexao.execute(
        """
        SELECT u.*, p.nome AS pessoa_nome
        FROM usuario u
        LEFT JOIN pessoa p ON p.id = u.pessoa_id
        ORDER BY u.ativo DESC, u.papel, u.login
        """
    )]


def sobra_outro_admin(conexao, usuario_id: int) -> bool:
    """
    Se este usuário parar de ser admin ativo, ainda existe outro? É a trava que
    impede a coordenação de se trancar fora do próprio sistema.
    """
    return conexao.execute(
        "SELECT COUNT(*) c FROM usuario "
        "WHERE papel = 'admin' AND ativo = 1 AND id <> ?",
        (usuario_id,),
    ).fetchone()["c"] > 0


def sem_acento(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if not unicodedata.combining(c))


def sugerir_login(conexao, nome: str) -> str:
    """
    Monta um login a partir do nome: primeiro nome + último sobrenome.

    "Antonella Oliveira Souza" -> "antonella.souza". Em caso de repetição, vai
    somando número. Sem acento e sem espaço, porque login é coisa que se digita
    no celular com pressa.
    """
    partes = [p for p in sem_acento(nome).casefold().split() if p]
    if not partes:
        base = "usuario"
    elif len(partes) == 1:
        base = partes[0]
    else:
        base = f"{partes[0]}.{partes[-1]}"

    base = "".join(c for c in base if c.isalnum() or c == ".")

    candidato, contador = base, 1
    while conexao.execute("SELECT 1 FROM usuario WHERE login = ?",
                          (candidato,)).fetchone():
        contador += 1
        candidato = f"{base}{contador}"
    return candidato


def pessoas_sem_usuario(conexao) -> list[dict]:
    """Quem tem matrícula ativa e ainda não tem acesso ao sistema."""
    return [dict(l) for l in conexao.execute(
        """
        SELECT DISTINCT p.id, p.nome, p.data_nascimento
        FROM pessoa p
        JOIN matricula ma ON ma.pessoa_id = p.id AND ma.status = 'ativa'
        WHERE p.id NOT IN (SELECT pessoa_id FROM usuario WHERE pessoa_id IS NOT NULL)
        ORDER BY p.nome
        """
    )]


def senha_aleatoria() -> str:
    """Senha inicial curta o bastante pra digitar no celular. A pessoa troca depois."""
    return secrets.token_urlsafe(9)


def criar_usuario(conexao, login: str, senha: str, papel: str,
                  pessoa_id: int | None) -> str | None:
    """Cria o usuário. Devolve mensagem de erro, ou None se deu certo."""
    login = (login or "").strip()
    if not login:
        return "O login não pode ficar vazio."
    if " " in login:
        return "O login não pode ter espaço."
    if papel not in ("admin", "jogador"):
        return f"Papel desconhecido: {papel}."
    if len(senha or "") < MINIMO_SENHA:
        return f"A senha precisa de pelo menos {MINIMO_SENHA} caracteres."

    # Confiro antes de gravar pra dar mensagem boa. O banco também pegaria, pelo
    # UNIQUE COLLATE NOCASE, mas com um erro que não ajuda quem está na tela.
    if conexao.execute("SELECT 1 FROM usuario WHERE login = ?", (login,)).fetchone():
        return f"Já existe um acesso com o login {login!r}."

    conexao.execute(
        "INSERT INTO usuario (login, senha_hash, papel, pessoa_id) VALUES (?,?,?,?)",
        (login, hash_da_senha(senha), papel, pessoa_id),
    )
    conexao.commit()
    return None


def criar_acesso_inicial(conexao, login: str, pessoa_id: int) -> None:
    """
    Acesso de jogador criado no lote: nasce sem hash, e a senha inicial é a
    data de nascimento (ver senha_inicial_confere). Nada de hash aqui de
    propósito — dezenas de hashes numa requisição só foi o que derrubava o
    botão do lote em produção. Não faz commit: o lote comita uma vez no fim.
    """
    conexao.execute(
        "INSERT INTO usuario (login, senha_hash, papel, pessoa_id) VALUES (?,?,?,?)",
        (login, "", "jogador", pessoa_id),
    )


def definir_papel(conexao, usuario_id: int, papel: str) -> str | None:
    if papel not in ("admin", "jogador"):
        return f"Papel desconhecido: {papel}."

    atual = conexao.execute("SELECT * FROM usuario WHERE id = ?",
                            (usuario_id,)).fetchone()
    if atual is None:
        return "Esse acesso não existe."
    if atual["papel"] == "admin" and papel != "admin" \
            and not sobra_outro_admin(conexao, usuario_id):
        return ("Esse é o único administrador ativo. Promova outra pessoa antes "
                "de rebaixar este, senão ninguém consegue administrar o sistema.")

    conexao.execute("UPDATE usuario SET papel = ? WHERE id = ?", (papel, usuario_id))
    conexao.commit()
    return None


def definir_ativo(conexao, usuario_id: int, ativo: bool) -> str | None:
    if not ativo and not sobra_outro_admin(conexao, usuario_id):
        atual = conexao.execute("SELECT papel FROM usuario WHERE id = ?",
                                (usuario_id,)).fetchone()
        if atual and atual["papel"] == "admin":
            return ("Esse é o único administrador ativo. Desativar ele deixaria "
                    "o sistema sem ninguém para administrar.")

    conexao.execute("UPDATE usuario SET ativo = ? WHERE id = ?",
                    (1 if ativo else 0, usuario_id))
    conexao.commit()
    return None


def desativar_por_inatividade(conexao, hoje, dias: int = DIAS_INATIVIDADE) -> list[str]:
    """
    Desativa o acesso de jogador de quem está há mais de `dias` sem participar.

    Participar = presença ou falta justificada numa matrícula ativa. Quem nunca
    teve chamada conta a partir da data da matrícula, senão o recém-chegado
    cairia antes da primeira aula. Sem matrícula ativa nenhuma, desativa
    direto. Admin nunca entra na varredura. Devolve os logins desativados.
    """
    limite = (hoje - timedelta(days=dias)).isoformat()
    parados = conexao.execute(
        """
        SELECT u.id, u.login
        FROM usuario u
        WHERE u.papel = 'jogador' AND u.ativo = 1 AND u.pessoa_id IS NOT NULL
          AND (
            NOT EXISTS (SELECT 1 FROM matricula ma
                        WHERE ma.pessoa_id = u.pessoa_id AND ma.status = 'ativa')
            OR COALESCE(
                 (SELECT MAX(pr.data) FROM presenca pr
                  JOIN matricula ma ON ma.id = pr.matricula_id
                  WHERE ma.pessoa_id = u.pessoa_id AND ma.status = 'ativa'
                    AND pr.status IN ('presente', 'justificada')),
                 (SELECT MAX(ma.data_matricula) FROM matricula ma
                  WHERE ma.pessoa_id = u.pessoa_id AND ma.status = 'ativa')
               ) < ?
          )
        """,
        (limite,),
    ).fetchall()

    if parados:
        conexao.executemany("UPDATE usuario SET ativo = 0 WHERE id = ?",
                            [(p["id"],) for p in parados])
        conexao.commit()
    return [p["login"] for p in parados]


def definir_senha(conexao, usuario_id: int, senha: str) -> str | None:
    if len(senha or "") < MINIMO_SENHA:
        return f"A senha precisa de pelo menos {MINIMO_SENHA} caracteres."
    conexao.execute("UPDATE usuario SET senha_hash = ? WHERE id = ?",
                    (hash_da_senha(senha), usuario_id))
    conexao.commit()
    return None


def somente_admin(funcao):
    """
    Reforço para rotas sensíveis, além da guarda central.

    Redundante de propósito: a guarda central já barra, mas se alguém mexer na
    lista de rotas do jogador por engano, estas continuam fechadas.
    """
    @functools.wraps(funcao)
    def envelope(*args, **kwargs):
        if not e_admin():
            flash("Essa parte do sistema é da coordenação.", "erro")
            return redirect(url_for("minha_area"))
        return funcao(*args, **kwargs)
    return envelope
