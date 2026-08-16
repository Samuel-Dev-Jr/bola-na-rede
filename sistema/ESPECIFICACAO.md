# Especificação — acessos, frequência e avisos

Plano de implementação do segundo pacote de funcionalidades, escrito antes de
codar pra eu não me perder. A ordem das fases é por risco: primeiro o que está
quebrado em produção, depois o que é novo.

## O problema que disparou tudo isso

O botão "Criar acesso para 59 pessoas" derrubava a produção com Internal
Server Error. Fui medir: cada senha custa ~125 ms de hash na minha máquina —
o scrypt é lento DE PROPÓSITO, pra dificultar chute de senha. 59 senhas dão
7 segundos aqui; na instância grátis do Render, que tem uma fração de CPU,
isso passa fácil de um minuto, e o gunicorn mata qualquer requisição que passe
de 30 segundos. Como eu gravava um usuário por vez, as contas ficavam criadas
e mesmo assim a tela mostrava erro — o pior dos dois mundos.

A conclusão que mudou o desenho: **senha aleatória sorteada no lote era uma
má ideia desde o início**. Ninguém anota 59 senhas; elas iam pro lixo junto
com a resposta que ninguém viu.

## Fase 0 — consertar o lote (senha inicial = data de nascimento)

- No lote, o usuário nasce SEM hash (`senha_hash = ''`). A string vazia é o
  marcador de "esta conta ainda usa a senha inicial".
- A senha inicial é a data de nascimento da própria pessoa: `01022014` (também
  aceito com barras). Zero hash na criação — a requisição volta a ser
  instantânea, com qualquer quantidade de gente.
- No primeiro login, o sistema NÃO deixa a pessoa ir pra lugar nenhum antes de
  definir a senha dela de verdade (tela nova, `/senha-nova`). A partir daí o
  hash existe e o fluxo é o normal.
- A guarda disso fica no mesmo lugar das outras: `exigir_login`, central.
  Decorador por rota eu já descartei uma vez (fácil de esquecer), não volto.
- Data de nascimento é senha fraca, eu sei. Ela só vale até o primeiro acesso,
  só existe em conta de jogador (que enxerga apenas os próprios dados), e a
  alternativa real do Centro hoje é o caderno, que não tem senha nenhuma.
- Criar acesso individual não muda: senha digitada, mínimo de 8.

## Fase 1 — frequência na ficha da pessoa

A ficha já mostra as atividades e a tira de presenças, mas não responde "quanto
por cento"? Entra uma tabela de frequência: uma linha por atividade com
presenças, faltas, faltas justificadas e o percentual de presença, e uma linha
de total. Quem não tem matrícula nenhuma ganha um aviso com o caminho pra
matricular, em vez da seção vazia que fica hoje (testei com um cadastro novo e
a tela fica muda).

## Fase 2 — desativar acesso por inatividade

Regra da coordenação: quem está há mais de 30 dias sem participar não precisa
de login ativo. "Sem participar" ficou assim:

- sem nenhuma matrícula ativa → desativa;
- com matrícula, mas a última presença (ou falta justificada) tem mais de 30
  dias → desativa;
- nunca teve presença registrada → conta a partir da data da matrícula, senão
  o recém-chegado seria desativado antes da primeira chamada.

Só derruba conta de JOGADOR. Admin nunca entra na varredura. A varredura roda
quando a coordenação abre a tela de Acessos — o plano grátis do Render não tem
agendador de tarefas, e amarrar na tela onde o resultado aparece é honesto:
quem desativou foi a coordenação ao abrir a tela, e ela vê o aviso de quantos
caíram. Reativar é o botão que já existia.

## Fase 3 — e-mail no cadastro e login por e-mail

- Coluna `email` na pessoa (opcional — é o e-mail do responsável). Migração
  aditiva; como `ALTER TABLE` não tem IF NOT EXISTS no SQLite, o db.py passa a
  conferir `PRAGMA table_info` antes de alterar.
- No login, o campo aceita o login OU o e-mail. Não removi o login: o e-mail é
  do responsável, e dois irmãos matriculados têm o MESMO e-mail — nesse caso o
  e-mail não identifica sozinho e cada um entra pelo seu login.
- A base de demonstração ganha e-mails fictícios em domínio reservado, pra dar
  pra testar o fluxo sem risco de e-mail cair na caixa de alguém de verdade.

## Fase 4 — envio de e-mail (novo módulo correio.py)

SMTP puro da biblioteca padrão, configurado por variável de ambiente
(`SMTP_SERVIDOR`, `SMTP_PORTA`, `SMTP_USUARIO`, `SMTP_SENHA`,
`SMTP_REMETENTE`). **Sem as variáveis, nada muda**: o sistema segue mostrando
a senha na tela pra entregar em mãos, que é o comportamento de hoje. Com elas:

- acesso criado → a pessoa recebe login e a instrução da senha inicial;
- senha alterada pela coordenação → a pessoa recebe a senha nova. O botão
  "Sortear nova senha" vira "Alterar senha", com campo pra escolher a senha
  (vazio continua sorteando).
- envio em lote sai numa thread, fora da requisição — senão o lote de 59
  esbarraria no MESMO timeout que motivou a fase 0, só que por SMTP.
- erro de envio nunca derruba a operação: a conta é criada/alterada e a tela
  avisa que o e-mail não saiu.

A vitrine no Render fica sem SMTP de propósito: base fictícia não manda
e-mail.

## Fase 5 — avisos para os participantes

Tabela `aviso` (modalidade, turma opcional, título, texto). O sistema registra
sozinho quando a coordenação cria um evento, publica um plano de treino ou
muda o horário — que é o que o participante precisa saber sem depender de
alguém repassar no grupo.

O jogador vê os avisos das turmas dele na "minha área", com selo de novo para
o que chegou depois da última visita (coluna `avisos_vistos_em` no usuário).
Se o SMTP estiver configurado, o aviso também sai por e-mail pra turma
afetada, na mesma thread do correio.

## O que fica de fora (e por quê)

- Notificação push de verdade (a PWA já existe, mas push exige serviço
  externo e chave VAPID — não entra na semana da entrega).
- Agendador pra varredura de inatividade — sem cron no plano grátis; a
  varredura na tela de Acessos resolve o caso real.
- Trocar o login pelo e-mail por completo — irmãos compartilham o e-mail do
  responsável, então o login continua existindo.
