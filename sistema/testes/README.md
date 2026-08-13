# Testes do Bola na Rede

O `testar_risco.py` roda sozinho, sem nada ligado. Os outros quatro precisam do
sistema rodando (`python app.py`) numa janela à parte.

Os dois primeiros são o que eu mais uso: são eles que pegam os erros que eu não
enxergo olhando a tela.

```bash
python testes/testar_risco.py       # a regra de evasão, sem banco e sem site
python testes/testar_acesso.py      # quem pode abrir o quê (login e papéis)
pip install playwright          # só o pacote; uso o Chrome que já está instalado
python testes/testar_escritas.py    # cadastro, matrícula, chamada, convocação
python testes/testar_layout.py      # estouro horizontal em 3 larguras
python testes/testar_contraste.py   # contraste WCAG de todos os textos
python testes/capturar_telas.py     # prints para o relatório e o vídeo
```

Desde que o sistema passou a exigir login, os testes precisam entrar antes de
medir. Isso está no `_acesso.py`, num lugar só: ele cria uma conta de teste com
senha aleatória, usa e apaga no fim. Se um script morrer no meio, sobra uma conta
com senha que ninguém conhece, e a execução seguinte a apaga.

> Se o login falhar, os scripts **param com erro** em vez de seguir. Sem isso
> eles mediriam a tela de entrar e passariam, dizendo que testaram outra coisa.

## O que cada um faz

**`testar_risco.py`** — testa a regra de evasão isolada, com 44 casos. Ele não
sobe o site nem abre o banco: a `avaliar_risco` é função pura, então dá pra
passar uma lista de presenças na mão e conferir a classificação. Todos os casos
usam uma data de referência fixa — com `date.today()` o teste passaria hoje e
quebraria semana que vem sem ninguém ter mexido na regra.

O que ele cobre que os outros não conseguem: as fronteiras exatas de 75% e 50%,
a ordem em que os `if` são testados, e as duas decisões sobre falta justificada
(não entra na frequência, e não zera nem soma na sequência de faltas).

> **Como eu soube que os casos valiam alguma coisa.** A primeira versão passava
> nos 39 casos, e isso não prova nada — teste que só passa pode estar testando
> o vazio. Então eu mudei a regra de propósito, numa cópia, pra ver se o teste
> reclamava: baixei `LIMITE_FREQUENCIA_ATENCAO` de 0.75 pra 0.70 e **nenhum caso
> falhou**. Eu testava 75% e 67%, e os dois ficam do mesmo lado dos dois
> limites. Faltava um caso entre 70% e 75%. Depois de arrumar, repeti para as 6
> constantes da regra e para as 2 decisões sobre justificada: as 8 alterações
> passaram a quebrar o teste.

**`testar_acesso.py`** — o teste de segurança do login. Entra como jogador e
tenta abrir cada tela da coordenação; falha se alguma abrir. Também confere que
senha errada e login inexistente dão a mesma resposta, para não contar a quem
tenta quais logins existem.

> Ele existe por causa de um erro meu. Na primeira versão da lista de rotas
> liberadas eu tinha incluído o painel da modalidade, pensando "é só leitura".
> Só que o painel tem o bloco "Ligar esta semana", com nome, nível de risco e
> **telefone do responsável** de quem está faltando. Este teste é o que garante
> que isso não volte.

**`testar_escritas.py`** — exercita as rotas que gravam no banco e confere o
efeito direto no SQLite. Confere, entre outras coisas, que refazer a chamada não
duplica linha, que matricular a mesma pessoa numa segunda modalidade não cria
uma pessoa nova, e que apagar a pessoa leva as matrículas junto.

> Ele liga `PRAGMA foreign_keys = ON` na conexão. O SQLite desliga chave
> estrangeira **por conexão**, e sem essa linha o teste de CASCADE dava falso
> negativo: acusava um erro que não existia no sistema.

**`testar_layout.py`** — abre cada tela em 390, 768 e 1440 px e acusa qualquer
elemento que ultrapasse a largura da janela. Falha também se alguma rota parar
de responder 200, porque já aconteceu de o teste passar testando página de erro
depois de eu renomear as rotas.

**`testar_contraste.py`** — lê a cor que o navegador **realmente pintou**,
compondo as camadas semitransparentes do vidro, e compara com o mínimo do WCAG
AA. Foi ele que mostrou que várias cores do sistema estavam abaixo do mínimo
desde o começo. Textos sobre gradiente ele pula e informa quantos, em vez de
inventar um número.

**`capturar_telas.py`** — gera os prints em `evidencias/telas`, no computador e
no celular.
