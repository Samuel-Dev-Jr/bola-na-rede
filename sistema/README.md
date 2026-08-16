# Centro de Cultura e Esportes

Sistema de gestão das atividades do Centro: futsal masculino e feminino e
jiu-jitsu.

Projeto de Extensão Curricularizada — UniFECAF
Análise e Desenvolvimento de Sistemas — 2026

Centro de Cultura e Esportes — Jardim Elizabete
R. Manoel Maria Fernandes, 580, Jardim Elizabete, Taboão da Serra/SP

## Como rodar

No Windows, é só dar dois cliques no `iniciar.bat`.

Pelo terminal:

```bash
pip install -r requirements.txt
python configurar.py     # só na primeira vez, cria o banco com as modalidades
python criar_usuario.py  # cria o primeiro acesso (coordenação)
python app.py            # abre em http://localhost:5000
```

O sistema pede login. São dois papéis:

| Papel | O que vê |
|---|---|
| **admin** | tudo: cadastro, chamada, convocação, importação de planilha |
| **jogador** | só o dele: atividades, horário do treino, frequência, jogos e se está convocado |

O primeiro administrador nasce por linha de comando (`python criar_usuario.py`)
e não por tela: uma página de "crie o primeiro admin" ficaria aberta na rede
local para quem chegasse primeiro. Depois disso, os outros usuários se criam
pelo sistema.

Em uso de verdade, defina a chave que assina a sessão — sem ela o sistema sorteia
uma nova a cada início e todo mundo é desconectado quando o servidor reinicia:

```bash
set CENTRO_CHAVE=uma-string-longa-e-aleatoria
```

Não precisa de Node, nem de servidor de banco, nem de internet. O banco é um
arquivo só (`centro.db`) e as fontes são as que já vêm no computador,
porque o técnico usa o sistema na beira do campo, onde às vezes não pega sinal.

O `configurar.py` cria o banco com as 3 modalidades e as 11 turmas do Centro, e
**sem nenhuma pessoa**. O cadastro entra de duas formas: pela tela, uma pessoa
por vez, ou em lote a partir de planilha:

**Pela tela:** menu `Configurações`, no topo. Envie um CSV por vez, as
matrículas primeiro e a chamada depois. A tela mostra o que já está no banco,
quantas linhas entraram e, quando algo dá errado, qual linha e por quê.

**Pelo terminal:**

```bash
python importar.py dados/matriculas.csv                       # cadastro
python importar.py dados/matriculas.csv dados/presencas.csv    # + chamada
```

Os modelos das planilhas estão em `dados/`. O `presencas.csv` segue a forma do
caderno de papel — nome na vertical, uma coluna por data, `P`, `F` ou `J` na
célula — porque foi transcrevendo o caderno que a base nasceu. Reimportar o
mesmo arquivo não duplica nada, então dá para corrigir a planilha e rodar de
novo.

Os arquivos `dados/demonstracao-*.csv` são uma **base de demonstração**: 62
pessoas com dados fictícios, para o sistema ter o que exibir em print e em
apresentação. Não são as pessoas do Centro. Estão marcados no nome justamente
para não serem confundidos com cadastro real.

Evento de jogo não vem por planilha: cria-se pela tela, em
`Convocação → Novo evento`.

## No ar (vitrine)

**https://bola-na-rede.onrender.com** — entra com a conta de coordenação.

A configuração de deploy está em `sistema/render.yaml`. Ela sobe uma **instância
de demonstração**, e é importante entender o que isso significa antes de usar.

> No Render, o campo *Blueprint Path* precisa apontar para `sistema/render.yaml`:
> ele procura na raiz do repositório por padrão, e o arquivo está na subpasta.

O plano gratuito do Render **não tem disco persistente**: o sistema de arquivos
volta ao estado do deploy a cada reinício, e o banco é um arquivo. Ele é apagado.
Por isso o `startCommand` roda o `preparar_deploy.py`, que reconstrói a base
fictícia a cada início — 62 pessoas, a chamada de julho até hoje e três jogos de
exemplo. **O que for digitado na instância hospedada se perde no próximo
reinício.**

Isso é aceitável porque a instância hospedada é vitrine: serve pra mostrar o
sistema funcionando, com dados inventados. Se a coordenação usar pra valer, roda
no computador do Centro, onde o banco persiste e onde as escolhas de segurança da
seção 4 do [DECISOES.md](DECISOES.md) fazem sentido.

> **A instância hospedada nunca recebe o caderno real.** Nome de criança,
> telefone de responsável e ficha médica não vão pra servidor de terceiro.

O que precisa estar definido no Render:

| Variável | Para quê |
|---|---|
| `ADMIN_SENHA` | senha do administrador. Sem ela o deploy aborta de propósito |
| `ADMIN_LOGIN` | login do administrador (padrão `coordenacao`) |
| `CENTRO_CHAVE` | assina o cookie de sessão. O `render.yaml` pede pro Render sortear |

Duas coisas a saber: a instância gratuita **hiberna** depois de ~15 minutos sem
acesso e leva perto de um minuto pra acordar — abra o link antes de apresentar. E
como a chave de sessão é sorteada em cada deploy, publicar de novo desconecta
todo mundo.

## O que cada tela resolve

Cada módulo saiu de uma dor que a coordenação me contou:

| Tela | Problema que ela resolve |
|---|---|
| Painel | A escolinha só descobria que uma criança tinha parado de vir dois meses depois |
| Alunos | Cadastro no caderno e ficha médica em papel solto, que ninguém achava na hora |
| Chamada | Chamada na folha, que depois ninguém somava |
| Agenda | Treino que aconteceu e ninguém lançou a chamada: o aluno sai do cálculo de frequência e o alerta de evasão atrasa |
| Convocação | Convocação bagunçada no WhatsApp, criança faltando no dia do jogo |
| Treinos | "O que a gente vai treinar hoje?" só existia no caderno do professor, e quem faltava não sabia o que perdeu |
| Minha área | O participante dependia de perguntar pra saber horário, frequência e se foi convocado |

A **escalação**, dentro da tela de convocação, é a única parte que não saiu de
uma conversa com a coordenação: foi ideia minha, e está marcada assim de
propósito. Ela mostra o time no campo, com número da camisa e posição, e quem
está no banco. Se eles usarem e disserem que não serve, sai.

As decisões de projeto — por que pessoa e matrícula são tabelas separadas, de
onde saíram os números da regra de risco, por que não tem cobrança e o que o
LGPD exigiria antes de usar isto para valer — estão em [DECISOES.md](DECISOES.md).

## Organização dos arquivos

```
app.py         as rotas do Flask
consultas.py   tudo que lê do banco
risco.py       a regra que classifica o risco de evasão
autenticacao.py login, papéis e quem pode abrir o quê
criar_usuario.py cria acesso pelo terminal (o primeiro admin)
metricas.py    recalcula as métricas de impacto lendo o banco
escalacao.py   as posições de cada esporte, pra montar o time no campo
db.py          conexão com o SQLite
configurar.py  cria o banco com as modalidades e turmas do Centro
importar.py    carrega cadastro e chamada a partir de planilha CSV
preparar_deploy.py monta a base de demonstração da vitrine hospedada
dados/         os modelos de planilha
schema.sql     criação das tabelas
migracoes.sql  o que veio depois do schema, sem apagar banco em uso
```

`schema.sql` e `migracoes.sql` são separados porque o primeiro começa com
`DROP TABLE`: ele só serve pra banco novo. Tabela que nasce depois entra no
`migracoes.sql`, em `CREATE ... IF NOT EXISTS`, e é aplicada a cada início — se
atualizar o sistema custasse o semestre de chamada já digitada, ninguém
atualizaria.

Separei `consultas.py` e `risco.py` do `app.py` porque no começo eu tinha
deixado tudo junto e não achava mais nada.

## A regra de risco

Está em `risco.py` e olha os últimos 30 dias:

| Situação | Quando acontece |
|---|---|
| Regular | frequência de 75% ou mais |
| Atenção | frequência entre 50% e 75%, ou 2 faltas seguidas |
| Risco de evasão | frequência abaixo de 50%, ou 3 faltas seguidas ou mais |
| Evadido | sem nenhuma presença há mais de 30 dias |

Falta justificada eu trato diferente das outras: ela não entra na conta da
frequência nem soma na sequência de faltas seguidas. Se a mãe avisou que a
criança está doente, isso não é sinal de que ela vai abandonar a escolinha.

## O que ficou de fora

- Esta lista dizia "não tem login". Tem: a coordenação entra como `admin` e o
  participante como `jogador`, e a lista de rotas do jogador é de permissão, não
  de proibição — rota nova nasce fechada. Ficou aqui desatualizado por um tempo.
- O horário de treino se edita pela tela, mas ele tem duas metades que o sistema
  não amarra uma na outra: os dias marcados (que a chamada e a agenda usam) e o
  texto que aparece pra quem lê. Dá pra marcar segunda e escrever "Ter e Qui" —
  o sistema aceita. Amarrar os dois exigiria gerar o texto a partir dos dias, e
  aí se perderia o "Sáb, 8h às 11h" que a coordenação escreve à mão.
- O cálculo de risco carrega todas as presenças na memória. O custo cresce com o
  número de presenças, não com o de pessoas, então é o histórico acumulado que
  vai apertar primeiro, não o tamanho da escolinha. Ainda não medi com a base
  real: quando ela estiver carregada, o `metricas.py` mede.
- Não tem controle financeiro nenhum, e isso é de propósito. O projeto é um
  grupo comunitário informal, sem CNPJ, e as atividades são gratuitas. Um
  sistema que controlasse cobrança daria a entender que existe pessoa jurídica
  por trás, e não existe.
