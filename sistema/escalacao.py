"""
As posições em campo de cada esporte, e onde elas ficam desenhadas.

Separei num arquivo próprio pelo mesmo motivo do risco.py: é conhecimento sobre
o assunto, não sobre o sistema. Quem entende de vôlei consegue conferir a
rotação aqui sem ler uma linha de Flask.

Cada esporte tem sua geometria e não dá pra usar um desenho só:

    futsal     5 em quadra, no losango com pivô na frente
    futebol    11 em campo, formação 4-4-2
    vôlei      6 em quadra, na rotação numerada de 1 a 6
    basquete   5 em quadra, por função (armador, ala, pivô)

Só o futsal está em uso hoje. Deixei os outros três porque o Centro já teve
vôlei e basquete e pode voltar a ter, e porque o futebol de campo é o que o
projeto era em 2019. Apagar o mapa não devolve tempo nenhum e me obrigaria a
redesenhar tudo se uma modalidade voltar.

As coordenadas são porcentagens dentro do desenho, com (0,0) no canto superior
esquerdo. O ataque é sempre pra cima: o gol/rede do adversário fica no topo.
Uso porcentagem e não pixel pra o mesmo desenho servir em qualquer tamanho de
tela, do celular de 390px ao monitor.
"""

# Cada posição: (código, rótulo curto, nome por extenso, x%, y%)
#
# O código é o que vai pro banco. Os rótulos são pro técnico ler no campo, e o
# nome por extenso entra no title, pra quem não conhece a abreviação.

# O futsal é jogado com 5 em quadra, e a formação mais comum na base é o
# losango: um fixo na defesa, dois alas nas laterais e o pivô mais à frente,
# de costas pro gol. Eu tinha copiado as 11 posições do futebol de campo e
# ficava errado de um jeito que qualquer um que joga percebe na hora — a tela
# pedia zagueiro e volante numa quadra de 40 metros.
FUTSAL = [
    ("GOL",  "GOL", "Goleiro",         50, 86),
    ("FIX",  "FIX", "Fixo",            50, 64),
    ("ALA-D", "AD", "Ala direito",     80, 44),
    ("ALA-E", "AE", "Ala esquerdo",    20, 44),
    ("PIV",  "PIV", "Pivô",            50, 22),
]

FUTEBOL = [
    ("GOL",   "GOL", "Goleiro",          50, 88),
    ("LAT-D", "LD",  "Lateral direito",  85, 68),
    ("ZAG-D", "ZAG", "Zagueiro direito", 63, 72),
    ("ZAG-E", "ZAG", "Zagueiro esquerdo", 37, 72),
    ("LAT-E", "LE",  "Lateral esquerdo", 15, 68),
    ("VOL",   "VOL", "Volante",          50, 54),
    ("MEI-D", "MD",  "Meia direita",     78, 44),
    ("MEI-E", "ME",  "Meia esquerda",    22, 44),
    ("MEI-C", "MEI", "Meia central",     50, 36),
    ("ATA-D", "ATA", "Atacante direito", 65, 18),
    ("ATA-E", "ATA", "Atacante esquerdo", 35, 18),
]

# No vôlei as posições são numeradas e a rotação é no sentido horário: quem está
# no 1 (saque, fundo direita) vai pro 6, depois 5, e assim por diante. Mantenho
# os números porque é assim que o técnico fala — "entra no 4", não "entra na
# ponta esquerda da frente".
VOLEI = [
    ("V4", "4", "Ponta esquerda (rede)",   25, 26),
    ("V3", "3", "Meio de rede",            50, 22),
    ("V2", "2", "Ponta direita (rede)",    75, 26),
    ("V5", "5", "Fundo esquerda",          25, 68),
    ("V6", "6", "Fundo meio",              50, 74),
    ("V1", "1", "Fundo direita (saque)",   75, 68),
]

BASQUETE = [
    ("ARM", "PG", "Armador",        50, 78),
    ("ALA-D", "SG", "Ala-armador",  80, 56),
    ("ALA-E", "SF", "Ala",          20, 56),
    ("PIV-D", "PF", "Ala-pivô",     66, 28),
    ("PIV", "C", "Pivô",            34, 28),
]

# Qual conjunto cada modalidade usa. A chave é o slug do banco.
POR_MODALIDADE = {
    "futsal-masculino": ("futsal", FUTSAL),
    "futsal-feminino": ("futsal", FUTSAL),
    # As de baixo não existem no Centro hoje. Ficam mapeadas porque o mapa não
    # atrapalha: para_modalidade() só é consultado pelo slug que está no banco.
    #
    # Cuidado com estas quatro linhas: quando renomeei futebol para futsal com
    # um replace no projeto inteiro, elas viraram "futsal-masculino" também. O
    # Python aceita chave repetida sem reclamar e fica com a ÚLTIMA, então o
    # futsal passou a carregar as 11 posições do futebol de campo — justo o
    # defeito que o renomear existia pra corrigir. Só apareceu porque eu abri o
    # arquivo pra conferir.
    "futebol-masculino": ("futebol", FUTEBOL),
    "futebol-feminino": ("futebol", FUTEBOL),
    "volei-masculino": ("volei", VOLEI),
    "volei-feminino": ("volei", VOLEI),
    "basquete-masculino": ("basquete", BASQUETE),
    "basquete-feminino": ("basquete", BASQUETE),
}


def para_modalidade(slug: str):
    """
    (tipo_de_quadra, posições) da modalidade, ou (None, []) se ela não escala.

    O jiu-jitsu cai no segundo caso: não tem time em quadra, e por isso também
    não tem convocação. Devolver lista vazia deixa a tela decidir sem precisar
    saber quais esportes são coletivos.
    """
    return POR_MODALIDADE.get(slug, (None, []))


def rotulo_da_posicao(slug: str, codigo: str) -> str:
    """O nome por extenso, pra mostrar na lista de convocados."""
    _, posicoes = para_modalidade(slug)
    for cod, _curto, nome, _x, _y in posicoes:
        if cod == codigo:
            return nome
    return codigo


def codigos_validos(slug: str) -> set:
    _, posicoes = para_modalidade(slug)
    return {p[0] for p in posicoes}
