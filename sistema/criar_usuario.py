"""
Cria um usuário do sistema pelo terminal.

Existe por um motivo só: o PRIMEIRO administrador. Sem nenhum usuário no banco
ninguém consegue entrar, e eu não quis resolver isso com uma tela de "crie o
primeiro admin" — ela ficaria aberta na rede local pra quem chegasse primeiro.

Depois que existe um admin, os outros usuários se criam pela tela.

Uso:
    python criar_usuario.py                 pergunta tudo
    python criar_usuario.py --listar        mostra quem já existe

A senha é pedida sem eco no terminal e nunca é gravada: guardo só o hash.
"""

import getpass
import sys

import autenticacao
import db

# Uma fonte só para o mínimo, senão o terminal e a tela discordariam.
MINIMO_SENHA = autenticacao.MINIMO_SENHA


def listar(conexao) -> None:
    linhas = conexao.execute(
        """
        SELECT u.login, u.papel, u.ativo, u.ultimo_acesso, p.nome AS pessoa
        FROM usuario u
        LEFT JOIN pessoa p ON p.id = u.pessoa_id
        ORDER BY u.papel, u.login
        """
    ).fetchall()

    if not linhas:
        print("Nenhum usuário cadastrado.")
        return

    print(f"{'login':<20} {'papel':<9} {'ativo':<6} {'pessoa vinculada':<28} último acesso")
    print("-" * 92)
    for l in linhas:
        print(f"{l['login']:<20} {l['papel']:<9} "
              f"{'sim' if l['ativo'] else 'não':<6} "
              f"{(l['pessoa'] or '—'):<28} {l['ultimo_acesso'] or 'nunca'}")


def perguntar_pessoa(conexao):
    """Pergunta a qual pessoa vincular. Vazio deixa sem vínculo."""
    print("\nVincular a uma pessoa do Centro? Isso é o que faz a área do jogador")
    print("mostrar as atividades dela. Deixe vazio para não vincular.")
    busca = input("  Parte do nome (ou vazio): ").strip()
    if not busca:
        return None

    achados = conexao.execute(
        "SELECT id, nome, data_nascimento FROM pessoa WHERE nome LIKE ? "
        "ORDER BY nome LIMIT 15",
        (f"%{busca}%",),
    ).fetchall()

    if not achados:
        print("  Ninguém com esse nome. Seguindo sem vínculo.")
        return None

    print()
    for i, p in enumerate(achados, 1):
        print(f"  {i}. {p['nome']} ({p['data_nascimento']})")

    escolha = input("  Número (ou vazio para nenhum): ").strip()
    if not escolha.isdigit() or not 1 <= int(escolha) <= len(achados):
        print("  Seguindo sem vínculo.")
        return None
    return achados[int(escolha) - 1]["id"]


def main(argumentos: list[str]) -> int:
    if not db.banco_existe():
        print("Banco não encontrado. Rode `python configurar.py` primeiro.")
        return 1

    conexao = db.conectar()
    try:
        if "--listar" in argumentos:
            listar(conexao)
            return 0

        primeiro = not autenticacao.existe_algum_usuario(conexao)
        if primeiro:
            print("Nenhum usuário existe ainda — este será o administrador.")
        else:
            listar(conexao)
            print()

        login = input("Login (sem espaço, sem acento): ").strip()
        if not login:
            print("Login vazio. Cancelado.")
            return 1
        if " " in login:
            print("Login não pode ter espaço. Cancelado.")
            return 1

        if autenticacao.buscar_por_login(conexao, login) is not None:
            print(f"Já existe um usuário {login!r}. Cancelado.")
            return 1

        if primeiro:
            papel = "admin"
        else:
            resposta = input("Papel — [a]dmin ou [j]ogador: ").strip().casefold()
            if resposta.startswith("a"):
                papel = "admin"
            elif resposta.startswith("j"):
                papel = "jogador"
            else:
                print("Papel não reconhecido. Cancelado.")
                return 1

        senha = getpass.getpass("Senha (não aparece na tela): ")
        if len(senha) < MINIMO_SENHA:
            print(f"Senha curta: mínimo {MINIMO_SENHA} caracteres. Cancelado.")
            return 1
        if senha != getpass.getpass("Repita a senha: "):
            print("As senhas não são iguais. Cancelado.")
            return 1

        pessoa_id = perguntar_pessoa(conexao)

        conexao.execute(
            "INSERT INTO usuario (login, senha_hash, papel, pessoa_id) VALUES (?,?,?,?)",
            (login, autenticacao.hash_da_senha(senha), papel, pessoa_id),
        )
        conexao.commit()

        print(f"\nUsuário {login!r} criado como {papel}.")
        if primeiro:
            print("Agora dá pra entrar no sistema e criar os outros pela tela.")
        return 0
    finally:
        conexao.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
