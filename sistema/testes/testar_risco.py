"""
Testa a regra de risco de evasão sozinha, sem subir o site nem tocar no banco.

A `avaliar_risco` é função pura: recebe uma lista de presenças e uma data de
referência, e devolve a classificação. Por isso ela é a única parte do projeto
que dá pra testar assim, e é justamente a parte que mais precisa: o resultado
depende da ORDEM dos ifs e do tratamento da falta justificada, e nenhuma das
duas coisas aparece olhando a tela.

Todos os casos usam uma data de referência fixa. Se eu usasse date.today() o
teste passaria hoje e quebraria semana que vem sem ninguém ter mexido na regra.
"""

import sys
from datetime import date
from pathlib import Path

# Rodando como "python testes/testar_risco.py", o sys.path começa em testes/.
# Aponto pra pasta de cima pra achar o risco.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from risco import (  # noqa: E402
    DIAS_PARA_EVASAO,
    JANELA_DIAS,
    PRIORIDADE_RISCO,
    ROTULO_RISCO,
    RegistroPresenca,
    avaliar_risco,
)

REFERENCIA = date(2026, 8, 12)

falhas = []


def checar(rotulo, condicao, detalhe=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {rotulo}"
          + (f" -- {detalhe}" if detalhe and not condicao else ""))
    if not condicao:
        falhas.append(rotulo)


def dias_atras(n):
    return date.fromordinal(REFERENCIA.toordinal() - n)


def dias_frente(n):
    return date.fromordinal(REFERENCIA.toordinal() + n)


LETRAS = {"P": "presente", "F": "falta", "J": "justificada"}


def serie(padrao, passo=2):
    """
    Monta presenças recuando no tempo, uma a cada `passo` dias.

    O ÚLTIMO caractere é o treino mais recente, que cai na data de referência.
    P = presente, F = falta, J = falta justificada. Escrever "PPFJF" é bem mais
    fácil de conferir do que montar seis RegistroPresenca na mão.
    """
    ultimo = len(padrao) - 1
    return [
        RegistroPresenca(dias_atras((ultimo - i) * passo), LETRAS[c])
        for i, c in enumerate(padrao)
    ]


def avaliar(padrao, passo=2):
    return avaliar_risco(serie(padrao, passo), REFERENCIA)


# --------------------------------------------------------- os quatro níveis
print("\n1. Os quatro níveis")

av = avaliar("PPPPPPPP")
checar("100% de presença = regular", av.nivel == "regular", av.nivel)
checar("frequência bate 100%", av.frequencia_pct == 100, av.frequencia_pct)

av = avaliar("FPFPPP")
checar("67% = atenção", av.nivel == "atencao", f"{av.nivel} / {av.frequencia_pct}%")

av = avaliar("FFPFFP")
checar("33% = risco de evasão", av.nivel == "risco", f"{av.nivel} / {av.frequencia_pct}%")
checar("motivo cita a frequência", "33%" in av.motivo, av.motivo)

av = avaliar_risco([RegistroPresenca(dias_atras(40), "presente")], REFERENCIA)
checar("sem presença há 40 dias = evadido", av.nivel == "evadido", av.nivel)
checar("motivo cita os dias", "40 dias" in av.motivo, av.motivo)

av = avaliar("FFFF")
checar("nunca teve presença = evadido", av.nivel == "evadido", av.nivel)
checar("motivo diz que nunca registrou",
       "Nunca registrou" in av.motivo, av.motivo)

# ------------------------------------------------------ fronteiras da regra
# O README promete "75% ou mais = regular" e "entre 50% e 75% = atenção". Esses
# casos são os que provam que o `<` do código concorda com o texto.
#
# Cada fronteira precisa de DOIS casos: um em cima dela e um no degrau logo
# abaixo. Na primeira versão eu tinha só o de cima, e mutei a constante de
# propósito pra conferir: baixar o limite de 0.75 pra 0.70 não fazia nenhum
# caso falhar. Testar 75% e 67% não pega isso, porque os dois ficam do mesmo
# lado das duas versões do limite. Quem pega é um caso ENTRE 70% e 75%.
print("\n2. As fronteiras exatas de frequência")

av = avaliar("FPPP")
checar("75% cravado ainda é regular", av.nivel == "regular", av.nivel)
checar("e a frequência é 75% mesmo", av.frequencia_pct == 75, av.frequencia_pct)

av = avaliar("FFFPPPPPPPP")
checar("73% já cai em atenção", av.nivel == "atencao",
       f"{av.nivel} / {av.frequencia_pct}%")
checar("e a frequência é 73% (o degrau abaixo de 75)",
       av.frequencia_pct == 73, av.frequencia_pct)

av = avaliar("FFFPPPPPPPPPPP")
checar("79% é regular", av.nivel == "regular",
       f"{av.nivel} / {av.frequencia_pct}%")

# Os 50% precisam de um caso que TERMINE em presença. Se terminasse em falta, a
# regra das faltas seguidas resolvia antes e a fronteira de frequência nem
# chegava a ser consultada -- foi o erro da minha primeira versão.
av = avaliar("FPFPFP")
checar("50% cravado é atenção, não risco", av.nivel == "atencao",
       f"{av.nivel} / {av.frequencia_pct}%")
checar("e a frequência é 50% mesmo", av.frequencia_pct == 50, av.frequencia_pct)

av = avaliar("FFFFFFPPPPP")
checar("45% cai em risco", av.nivel == "risco",
       f"{av.nivel} / {av.frequencia_pct}%")
checar("e a frequência é 45% (o degrau abaixo de 50)",
       av.frequencia_pct == 45, av.frequencia_pct)

# ------------------------------------------------------ a falta justificada
# Esta é a parte humana da regra: se a mãe avisou que a criança está doente,
# isso não é sinal de que ela vai abandonar a escolinha.
print("\n3. A falta justificada")

com_j = avaliar("PJP")
checar("justificada não entra na conta da frequência",
       com_j.frequencia_pct == 100, com_j.frequencia_pct)
checar("e não derruba pra atenção", com_j.nivel == "regular", com_j.nivel)

av = avaliar("PJJJJ")
checar("4 justificadas seguidas continua regular", av.nivel == "regular", av.nivel)
checar("justificada não conta como falta seguida",
       av.faltas_consecutivas == 0, av.faltas_consecutivas)

# O trio abaixo é o coração do teste. Mesma posição, três conteúdos no meio:
#   F J F  -> a justificada é transparente: continua sendo 2 faltas seguidas
#   F F    -> as mesmas 2 faltas, sem nada no meio
#   F P F  -> a presença no meio ZERA a contagem, e aí é caso diferente
com_justificada = avaliar("PPPPPPFJF")
sem_nada = avaliar("PPPPPPFF")
com_presenca = avaliar("PPPPPPFPF")

checar("F J F conta 2 faltas seguidas",
       com_justificada.faltas_consecutivas == 2,
       com_justificada.faltas_consecutivas)
checar("F J F dá o mesmo nível que F F",
       com_justificada.nivel == sem_nada.nivel == "atencao",
       f"{com_justificada.nivel} vs {sem_nada.nivel}")
checar("F P F conta só 1 falta seguida",
       com_presenca.faltas_consecutivas == 1, com_presenca.faltas_consecutivas)
checar("e por isso F P F não vira atenção",
       com_presenca.nivel == "regular", com_presenca.nivel)

av = avaliar("FFFFP")
checar("falta ANTES da última presença não conta na sequência",
       av.faltas_consecutivas == 0, av.faltas_consecutivas)

# ------------------------------------------------------- a ordem dos ifs
# O próprio comentário do risco.py avisa: quem evadiu também bate na regra de
# atenção, e se atenção fosse testada primeiro ninguém seria evadido nunca.
print("\n4. A precedência entre os níveis")

av = avaliar_risco(
    [RegistroPresenca(dias_atras(40), "presente")]
    + [RegistroPresenca(dias_atras(d), "falta") for d in (6, 4, 2)],
    REFERENCIA,
)
checar("evadido ganha de risco quando os dois batem",
       av.nivel == "evadido", av.nivel)
checar("(a condição de risco estava mesmo satisfeita)",
       av.faltas_consecutivas == 3, av.faltas_consecutivas)

av = avaliar("PPPPPPFFF")
checar("3 faltas seguidas = risco, mesmo com 67% de frequência",
       av.nivel == "risco", f"{av.nivel} / {av.frequencia_pct}%")
checar("e o motivo é a sequência, não a frequência",
       "faltas seguidas" in av.motivo, av.motivo)

av = avaliar("PPPPPPPPFF")
checar("2 faltas seguidas = atenção, mesmo com 80% de frequência",
       av.nivel == "atencao", f"{av.nivel} / {av.frequencia_pct}%")

# ------------------------------------------- a borda dos 30 dias de evasão
# JANELA_DIAS e DIAS_PARA_EVASAO valem 30 os dois, e a regra é "> 30". Então
# 30 dias exatos ainda é classificado pela frequência; 31 já é evadido.
print(f"\n5. A borda da evasão (JANELA_DIAS={JANELA_DIAS}, "
      f"DIAS_PARA_EVASAO={DIAS_PARA_EVASAO})")

av = avaliar_risco([RegistroPresenca(dias_atras(30), "presente")], REFERENCIA)
checar("30 dias exatos ainda NÃO é evadido", av.nivel != "evadido", av.nivel)
checar("30 dias entra na janela de frequência",
       av.treinos_na_janela == 1, av.treinos_na_janela)

av = avaliar_risco([RegistroPresenca(dias_atras(31), "presente")], REFERENCIA)
checar("31 dias já é evadido", av.nivel == "evadido", av.nivel)
checar("e sai da janela de frequência",
       av.treinos_na_janela == 0 and av.frequencia is None,
       f"{av.treinos_na_janela} treinos / freq {av.frequencia}")

# ------------------------------------------------------ bordas defensivas
print("\n6. Bordas que já quebrariam o sistema")

av = avaliar_risco([], REFERENCIA)
checar("lista vazia não estoura", av.nivel == "evadido", av.nivel)
checar("lista vazia deixa a frequência em None (sem divisão por zero)",
       av.frequencia is None, av.frequencia)
checar("frequencia_pct também aguenta o None",
       av.frequencia_pct is None, av.frequencia_pct)

base = serie("PPPFFF")
futura = base + [RegistroPresenca(dias_frente(5), "presente")]
checar("presença lançada com data futura é ignorada",
       avaliar_risco(futura, REFERENCIA) == avaliar_risco(base, REFERENCIA))

checar("a ordem em que as presenças chegam não muda nada",
       avaliar_risco(list(reversed(base)), REFERENCIA)
       == avaliar_risco(base, REFERENCIA))

# ------------------------------------------------------------- os rótulos
print("\n7. Rótulos e prioridade de contato")

niveis = {"regular", "atencao", "risco", "evadido"}
checar("todo nível tem rótulo pra mostrar na tela",
       niveis <= ROTULO_RISCO.keys(), sorted(niveis - ROTULO_RISCO.keys()))
checar("todo nível tem prioridade de contato",
       niveis <= PRIORIDADE_RISCO.keys(), sorted(niveis - PRIORIDADE_RISCO.keys()))
checar("quem está sumindo agora vem antes de quem já sumiu",
       PRIORIDADE_RISCO["risco"] < PRIORIDADE_RISCO["evadido"],
       f"risco={PRIORIDADE_RISCO['risco']} evadido={PRIORIDADE_RISCO['evadido']}")

print("\n" + "=" * 56)
if falhas:
    print(f"{len(falhas)} caso(s) falharam:")
    for f in falhas:
        print(f"  - {f}")
else:
    print("A regra de risco passou em todos os casos.")
sys.exit(1 if falhas else 0)
