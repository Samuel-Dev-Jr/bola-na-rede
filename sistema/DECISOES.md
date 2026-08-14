# Decisões de projeto — Bola na Rede

Projeto de Extensão Curricularizada — UniFECAF
Análise e Desenvolvimento de Sistemas — 2026

Este documento reúne as decisões que não dá para ver rodando o sistema. Elas
estão comentadas no código, cada uma no arquivo onde importa, mas comentário
espalhado não conta a linha de raciocínio inteira. Aqui está o porquê de cada
escolha, e principalmente o que eu escolhi **não** fazer.

O que eu tento deixar claro em cada item: qual era o problema real da
coordenação, o que eu tentei primeiro, e por que mudei.

---

## 1. Separar PESSOA de MATRÍCULA

Essa foi a mudança mais importante do banco, e ela veio de um erro meu.

Na primeira versão cada linha de aluno pertencia a uma modalidade só. Parecia
óbvio: uma tabela `atleta`, com uma coluna apontando pra turma. Só que mais da
metade das crianças do Centro faz mais de uma atividade — hoje são 32 de 58.
Do jeito antigo, quem jogava futebol e basquete virava **duas pessoas** no
banco, com o telefone digitado duas vezes e a ficha médica preenchida em uma e
vazia na outra.

Quando eu percebi isso, percebi também o que tinha acontecido: eu havia copiado
para o banco exatamente o problema do caderno de papel que o sistema deveria
resolver. No caderno, cada modalidade tem a sua folha, e a mesma criança aparece
em três folhas diferentes com dados que não conversam.

O modelo de hoje:

```
pessoa  ──┐
          ├── matricula ── presenca
turma   ──┘
```

`matricula` é tabela associativa entre pessoa e turma. E a **presença é da
matrícula, não da pessoa** — porque frequência é por modalidade: dá para ser
assíduo no futebol e estar sumindo do basquete, e a coordenação precisa ver as
duas coisas separadas para saber com quem falar.

Consequência prática nas rotas: a ficha da pessoa vive em `/pessoas/<id>`, fora
da modalidade, porque ela junta todas as atividades dela. O resto vive em
`/m/<slug>/...`, porque é sempre a respeito de uma modalidade específica.

**O número da camisa mostrou que a separação estava certa.** Quando fui
acrescentar número de camisa, o campo caiu na `matricula` sem discussão: número
é do time, não do ser humano. A mesma criança pode ser 10 no futebol e 7 no
basquete, e no karatê não usar número nenhum. Se a tabela ainda fosse a `atleta`
da primeira versão, isso funcionaria por acidente — porque lá cada linha já era
uma modalidade — e quebraria na primeira vez que alguém tentasse consertar a
duplicação de cadastro.

A unicidade veio junto, e num detalhe que eu não esperava: o índice tem que ser
**parcial**.

```sql
CREATE UNIQUE INDEX idx_matricula_numero
    ON matricula (turma_id, numero) WHERE numero IS NOT NULL;
```

Sem o `WHERE`, a segunda matrícula sem número seria recusada como repetida, e a
maioria não tem número. Com ele, dois `NULL` convivem e dois `10` no mesmo
Sub-13 não — que é exatamente a regra do mundo real.

## 2. A regra de risco de evasão

A dor que originou o projeto: hoje a escolinha só descobre que uma criança parou
de vir quando alguém comenta no treino, e isso leva **cerca de dois meses**. A
meta que eu combinei com a coordenação foi avisar em uma semana.

A regra está isolada em `risco.py`, separada de tudo. Isso não foi organização
por gosto: é o que me deixa testá-la sem subir o site nem abrir o banco, e é o
que me deixa explicá-la na apresentação sem abrir o Flask.

| Situação | Quando acontece |
|---|---|
| Regular | frequência de 75% ou mais |
| Atenção | frequência entre 50% e 75%, ou 2 faltas seguidas |
| Risco de evasão | frequência abaixo de 50%, ou 3 faltas seguidas ou mais |
| Evadido | sem nenhuma presença há mais de 30 dias |

**De onde saíram esses números.** Não saíram de fórmula nem de artigo. Eu
sentei com o coordenador em cima do caderno de chamada e perguntei de quem ele
ia atrás e por quê. Era mais ou menos assim que ele já decidia de cabeça. O
sistema não inventou um critério novo: ele automatizou o que já existia e não
escalava, porque dependia de o coordenador lembrar de folhear o caderno.

**Por que a ordem dos `if` importa.** Testo do caso mais grave para o mais leve.
Quem evadiu também satisfaz a condição de "atenção" — tem frequência baixa e
faltas seguidas. Se eu testasse atenção primeiro, ninguém seria classificado
como evadido nunca, e o sistema mostraria "atenção" para uma criança que saiu há
três meses. Isso é o tipo de erro que não aparece na tela: o número fica
plausível e errado.

**Por que falta justificada é tratada diferente.** Ela fica fora da conta dos
dois lados: não entra como presença nem como falta na frequência, e não soma nem
zera a sequência de faltas seguidas. Se a mãe avisou que a criança está doente,
isso não é sinal de que ela vai abandonar a escolinha — e se eu contasse como
falta, criança doente apareceria como risco de evasão. O sistema mandaria o
coordenador ligar para a família errada.

O caso que mostra isso melhor: `falta, justificada, falta` conta **2 faltas
seguidas**, e não 1 nem 3. A justificada é transparente. Já
`falta, presença, falta` conta 1, porque a presença zera de verdade.

**Por que "risco" vem antes de "evadido" na lista de contato.** A ordenação de
quem ligar primeiro não é pela gravidade. Quem está sumindo agora ainda dá para
segurar; quem já sumiu faz três meses é muito mais difícil de trazer de volta.
A lista é ordenada pelo que ainda tem chance de mudar de resultado.

## 3. O que eu tirei de propósito: cobrança

A primeira versão tinha uma tela de mensalidades, com valor arrecadado no mês e
situação de pagamento de cada criança. Eu tirei, e essa é uma decisão que eu
defendo, não uma funcionalidade que faltou.

O Bola na Rede é um grupo comunitário informal, **sem CNPJ**, e as atividades
são gratuitas. Um sistema que controla cobrança daria a entender que existe
pessoa jurídica por trás, e não existe. Além disso, a tela marcava criança por
criança quem estava com pagamento em aberto e quem era isento por
vulnerabilidade — ou seja, expunha a situação financeira da família de um menor
em uma tabela que qualquer pessoa com o link enxergava.

Ficou registrado no `schema.sql` que a tabela `mensalidade` foi retirada, e o
`DROP TABLE IF EXISTS mensalidade` continua no script — não por engano, mas
porque quem já tinha rodado a versão anterior precisa que ela seja apagada para
o banco ser recriado sem erro de chave estrangeira.

Os prints da versão antiga estão em `evidencias/telas/versao-anterior/`, para
registrar que a tela existiu e foi retirada por decisão de projeto.

## 3b. A base de demonstração é fictícia, e isso está declarado

Os arquivos `dados/demonstracao-matriculas.csv` e `demonstracao-presencas.csv`
têm 62 pessoas com nome, telefone e ficha médica **inventados**. Eles existem
para o sistema ter o que mostrar em print, em vídeo e em apresentação — um
sistema de gestão com o banco vazio não demonstra nada.

Duas razões para os dados serem fictícios em vez de reais, e a segunda é a que
manda:

1. Não tive tempo de transcrever o caderno inteiro antes da entrega.
2. **Colocar nome completo de criança, telefone de responsável e ficha médica
   real dentro de um arquivo que eu entrego para a faculdade contradiria a
   seção 4 deste documento.** Se eu defendo que esses dados são sensíveis e
   pedem cuidado, não posso anexá-los ao trabalho.

O nome do arquivo começa com `demonstracao-` de propósito: assim a procedência
aparece em qualquer lugar onde o arquivo apareça, sem depender de alguém lembrar
de explicar. Nenhum número tirado dessa base descreve o Centro real — as
métricas de campo estão em `evidencias/caderno-de-campo.md` e são medidas no
local.

**É essa decisão que tornou possível hospedar o sistema.** A instância em
https://bola-na-rede.onrender.com existe para o sistema poder ser aberto e
avaliado de qualquer lugar. Se a base fosse o caderno real, subir seria tirar
nome de criança, telefone de responsável e ficha médica da rede do Centro e
colocar em servidor de terceiro — exatamente o que a seção 4 diz que não se faz.
Com base fictícia, não há dado de ninguém lá.

A regra que fica: **a instância hospedada nunca recebe o caderno real.** Se a
coordenação usar o sistema para valer, aquilo roda no computador do Centro.

## 3c. A escalação, e por que ela é toque em vez de arrastar

A escalação mostra o time no campo — pentágono de posições, número da camisa,
quem está no banco. Ela vive na `convocacao` e não em tabela nova, porque é uma
propriedade da convocação: quem foi chamado e onde joga. **Convocado sem posição
É o reserva**, sem precisar de coluna pra isso.

Cada esporte tem geometria própria, em `escalacao.py`: 11 no futebol num 4-4-2,
6 no vôlei na rotação numerada de 1 a 6, 5 no basquete por função. Karatê e
pilates não escalam, e nem têm convocação.

**Toque, não arrastar.** Arrastar é o que parece natural num editor de escalação,
e eu não fiz assim de propósito: arrastar em celular é frágil, não tem caminho
por teclado, e o técnico está com uma mão no telefone na beira do campo com sol
na tela. Toque numa posição abre a lista de quem pode entrar. O abre-e-fecha é
`<details>` do HTML puro — zero JavaScript, zero biblioteca.

Três coisas que eu só descobri testando:

1. **Substituir tem que mandar o antigo pro banco, não pra fora.** Quando o
   técnico troca o goleiro, o goleiro antigo continua indo ao jogo. O lugar é que
   é único, não a pessoa.
2. **Salvar a lista de convocados apagava o time inteiro.** O `salvar_convocacao`
   apagava tudo e regravava — inofensivo antes de existir escalação, destrutivo
   depois: mexer num nome apagaria o time que o técnico acabou de montar. Agora
   ele só remove quem saiu e acrescenta quem entrou.
3. **O menu do goleiro abria fora da tela.** Ele fica a 88% da altura do campo, e
   o menu de 320px descia pra fora. Posições da metade de baixo agora abrem pra
   cima. Isso apareceu num print, não num teste — e é por isso que eu tiro print.

E um defeito que era da BASE, não do código: a demonstração espalhava 62 pessoas
por 24 turmas, dando umas quatro por turma. Só que time de futebol precisa de 11
**na mesma turma**. O Sub-13 ficou com 4 elegíveis pra 11 posições e um jogo
apontava pra turma vazia — a tela abria parecendo quebrada. Agora a base é
gerada por alvo, e o `preparar_deploy.py` avisa quando um jogo tem menos
elegíveis que posições.

## 4. Login e papéis — a lacuna que era a mais séria, e como fechei

Até a versão anterior esta seção começava com "não tem login", e era a limitação
mais grave do projeto. Agora tem, e o que sobrou de aprendizado é a parte que
vale ler.

**O que o sistema guarda.** Nome completo de criança e adolescente, data de
nascimento, telefone do responsável e ficha médica (alergia, condição de saúde,
medicação, contato de emergência).

**Por que isso é sensível.** Pela LGPD (Lei nº 13.709/2018), dado referente à
saúde é **dado pessoal sensível** (Art. 5º, II), e o tratamento de dados de
crianças e adolescentes tem regra própria: deve ser feito no melhor interesse
do titular e, no caso de consentimento, exige consentimento específico e em
destaque de pelo menos um dos pais ou do responsável legal (Art. 14). O Art. 6º
ainda impõe finalidade, necessidade e segurança; o Art. 46, medidas técnicas de
proteção.

**Como está agora.** Dois papéis, em `autenticacao.py`:

| Papel | Enxerga |
|---|---|
| `admin` | tudo: cadastro, chamada, convocação, importação de planilha |
| `jogador` | só a área dele: atividades, horário, frequência, jogos e se está convocado |

Senha guardada como hash `scrypt` do werkzeug, com sal por senha — nunca a senha.
A chave que assina a sessão saiu do código e virou variável de ambiente, porque
com login uma chave conhecida deixa qualquer um forjar cookie de admin.

**A verificação é central, não por decorador em cada rota.** Fica no
`before_request`, e a lista é de **permissão**: o que não está nela é negado. Com
22 rotas já existentes, decorador em cada uma seria fácil de esquecer numa rota
nova — e esquecer significaria deixar aberta. Assim, rota nova nasce fechada.

**O erro que eu cometi escrevendo isso, e é o mais instrutivo do projeto.** Na
primeira versão da lista eu tinha liberado o painel da modalidade pro jogador,
pensando "é só leitura, não faz mal". Faz. O painel tem o bloco *"Ligar esta
semana"*, com nome completo, nível de risco e **telefone do responsável** de quem
está faltando. Eu ia publicar, pra turma inteira, quem está em risco de evasão e
o telefone da mãe — dentro do mesmo projeto onde escrevi esta seção defendendo o
cuidado com esses dados.

A lição não é "faltou atenção". É que **tela de administrador não se reaproveita
para o participante só porque é leitura**. O que o jogador precisa ver vive em
tela própria, que mostra só o dele. E é por isso que o `testes/testar_acesso.py`
existe: ele tenta abrir, como jogador, cada tela da coordenação, e falha se
alguma abrir.

Outra decisão da mesma família: **a área do jogador não mostra o nível de risco.**
"Risco de evasão" é leitura que a coordenação faz para decidir com quem falar,
não rótulo para pendurar na criança quando ela abre o aplicativo. A frequência
ela vê; o julgamento sobre ela, não.

**O modo debug é parte desse problema, e eu só descobri testando.** O `app.py`
sobe com `app.run(debug=True)`, e isso tem duas consequências que eu não havia
pensado:

- O depurador do Werkzeug fica exposto. Ele executa código no servidor a partir
  do navegador. Num sistema sem login, na rede local, com ficha médica de menor
  dentro, isso é a porta mais larga que existe.
- O recarregador automático cria um processo filho. Ao fechar o terminal, o filho
  **continua vivo** segurando a porta 5000. Eu cheguei a ter cinco servidores
  escutando a mesma porta ao mesmo tempo, de dias diferentes — o Windows permite,
  e as conexões caem num deles de forma imprevisível. Durante um teste meu, uma
  tela nova respondia 404 porque a requisição foi atendida por um servidor de
  dois dias antes. Ou seja: **é possível testar código velho achando que é o
  novo.** Se um dia isso virar uso de verdade, `debug` tem que ser `False`.

**O que ainda falta antes de usar isto para valer**, e nessa ordem:

1. ~~Autenticação~~ — **feito.** Usuário por pessoa, com papel, não senha
   compartilhada.
2. **Registro de acesso** (quem abriu qual ficha e quando). Hoje gravo apenas o
   último acesso de cada conta. Sem o registro por ficha não há como responder a
   um pedido de prestação de contas.
3. **Base legal documentada**: na prática, o termo de autorização assinado pelo
   responsável na matrícula. Preciso confirmar com a coordenação como esse
   consentimento é coletado hoje no papel, porque o sistema precisa refletir isso
   e não criar uma coleta nova.
4. **Minimização**: hoje a ficha médica fica visível junto do cadastro, para
   qualquer admin. O que a coordenação precisa na beira do campo é contato de
   emergência e alergia grave; o resto poderia ficar em tela separada.
5. **Retenção**: nada é apagado. Precisa existir regra de por quanto tempo os
   dados de quem saiu continuam guardados.
6. **Política de senha e bloqueio por tentativas.** Hoje exijo 8 caracteres na
   criação e não limito tentativas de login — dá para ficar tentando senha à
   vontade. Numa rede local com poucas pessoas o risco é baixo, mas está aberto.
7. **`debug=False`**, pelo motivo do parágrafo acima.

Estou registrando o que falta porque o risco não desaparece por não estar
escrito. O que mudou nesta versão é que a lacuna número um saiu da lista.

## 5. Offline: o que o app deixa e o que ele recusa

O sistema é um PWA e funciona sem sinal, porque o técnico usa o celular na beira
do campo, onde às vezes não pega. As telas já abertas continuam disponíveis.

Mas ele **recusa** salvar chamada, matrícula ou convocação sem conexão. Isso é
deliberado e é o oposto do que a maioria dos apps faz. O motivo: se eu deixasse
gravar localmente e sincronizar depois, o técnico marcaria a chamada inteira
achando que gravou. Se a sincronização falhasse — e ela falha, é celular velho
em rede pública — a chamada estaria perdida e ninguém saberia. Uma chamada que
não existe é pior que uma chamada que não foi feita, porque a segunda o
coordenador percebe na tela de Agenda e refaz.

Também não uso fonte nem biblioteca de fora: as fontes são as que já existem no
computador. Sem internet, sem Node, sem servidor de banco.

## 6. Como eu sei que funciona

Cinco scripts em `testes/`. Os quatro primeiros existem porque pegam erros que
eu não enxergo olhando a tela.

| Teste | O que ele prova |
|---|---|
| `testar_risco.py` | A regra de evasão, 44 casos, sem site e sem banco |
| `testar_escritas.py` | As rotas de escrita gravam certo no SQLite |
| `testar_layout.py` | Nenhuma tela estoura a largura em 390, 768 e 1440 px |
| `testar_contraste.py` | Todo texto passa o mínimo do WCAG AA |
| `capturar_telas.py` | Gera os prints do relatório e do vídeo |

Três coisas que esses testes me ensinaram, e que eu não teria descoberto de
outro jeito:

**O SQLite desliga chave estrangeira por conexão.** O teste de `ON DELETE
CASCADE` acusava um erro que não existia: apagar a pessoa deixava matrícula
órfã. O bug estava no meu script de teste, que não ligava
`PRAGMA foreign_keys = ON` na própria conexão. O sistema estava certo, o teste
estava errado, e o resultado era um falso negativo — o tipo mais caro, porque
manda consertar o que não está quebrado.

**Várias cores estavam abaixo do mínimo de contraste desde o começo.** O
`testar_contraste.py` lê a cor que o navegador realmente pintou, compondo as
camadas semitransparentes do efeito de vidro, em vez de olhar o CSS. Foi assim
que apareceu. Olhando a tela eu achava tudo legível — no meu monitor, com a
minha idade, na luz do meu quarto.

**Teste que só passa não prova nada.** A primeira versão do `testar_risco.py`
passava em 39 casos. Para conferir se aqueles casos tinham alguma força, eu
alterei a regra de propósito numa cópia e vi se o teste reclamava: baixei o
limite de atenção de 0,75 para 0,70 e **nenhum caso falhou**. Eu testava 75% e
67%, e os dois ficam do mesmo lado dos dois limites — faltava um caso entre 70%
e 75%. Depois de corrigir, repeti o exercício com as 6 constantes da regra e as
2 decisões sobre falta justificada: as 8 alterações passaram a quebrar o teste.

## 7. Limites conhecidos

- **Não tem login.** Ver a seção 4, com o que faltaria.
- **O cálculo de risco carrega todas as presenças na memória.** O custo cresce
  com o número de presenças, não de pessoas, então é o histórico acumulado que
  aperta primeiro. Não tenho a medição com a base real ainda; o `metricas.py`
  mede quando ela estiver carregada.
- **Não tem controle financeiro nenhum**, de propósito. Ver a seção 3.
- **Não dá para trocar o número da camisa depois.** Ele é definido no momento da
  matrícula, ou em lote pela planilha (reimportar atualiza). Falta uma tela de
  editar matrícula, que hoje não existe para nada — nem para número, nem para
  turma. Quem precisar trocar o 10 pelo 9 corrige a planilha e reimporta.
- **A chamada valida o status, mas não a data.** O `salvar_chamada` só aceita
  `presente`, `falta` ou `justificada`, e descarta qualquer outra coisa que
  chegue no formulário. A data, não: dá para lançar presença em um dia que não
  tinha treino, e o calendário da Agenda vai mostrar aquele dia com número de
  presentes, porque ele decide se houve chamada olhando se existe lançamento,
  não se o dia tinha aula. A regra de risco ignora data no futuro — isso está
  coberto por teste — mas quem digita a data errada no passado não é avisado.
  Hoje isso é confiança no técnico, não validação, e é aceitável só enquanto o
  sistema roda com duas pessoas.
