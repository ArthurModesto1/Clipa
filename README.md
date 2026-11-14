# Clipa

Aplicativo desktop para baixar vídeos e áudios do **YouTube, X / Twitter,
Instagram e TikTok**, com processamento no próprio computador.

- Prévia com título, autor e duração, quando a plataforma disponibiliza esses dados.
- Vídeo em MP4, MKV ou WebM, com limite de resolução entre 360p e 4K.
- Áudio em MP3, AAC, Opus, FLAC ou WAV.
- Escolha da pasta, progresso, cancelamento e histórico local de até 100 downloads.
- Arquivo de sessão opcional para publicações que exigem login.
- Interface em português, sem fontes ou scripts externos.
- Temas claro e escuro em **Configurações → Aparência**, com preferência salva localmente.

O Clipa baixa uma publicação por vez, não perfis inteiros ou playlists. Em posts
com vários vídeos, utiliza o primeiro vídeo retornado pelo extrator. Fotos,
transmissões ao vivo em andamento e conteúdo protegido por DRM não são suportados.

## Instalação para desenvolvimento

Requisitos:

- Windows 10/11 como plataforma principal. Linux e macOS têm scripts de execução
  e build, mas ainda precisam de validação manual nessas plataformas.
- [Node.js](https://nodejs.org/) 22 ou superior e npm.
- [Python](https://www.python.org/downloads/) 3.11 ou superior.
- [FFmpeg e FFprobe](https://ffmpeg.org/download.html) disponíveis no PATH.
- Git para clonar o repositório.

Após clonar este repositório e entrar na pasta do projeto, no PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r python/requirements.txt
npm ci
npm start
```

Não é necessário ativar o ambiente virtual: o Clipa detecta `.venv` automaticamente.
No macOS/Linux, substitua as duas primeiras linhas por:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r python/requirements.txt
```

Confira as ferramentas antes de iniciar:

```powershell
node --version
python --version
ffmpeg -version
ffprobe -version
```

Se uma ferramenta foi instalada com o terminal aberto, reabra o terminal. Para
escolher outro interpretador no PowerShell:

```powershell
$env:CLIPA_PYTHON = 'C:\caminho\python.exe'
npm start
```

Em redes com certificados locais, se o npm retornar `UNABLE_TO_VERIFY_LEAF_SIGNATURE`,
use Node.js 24 e habilite a confiança nos certificados do sistema apenas no terminal atual:

```powershell
$env:NODE_USE_SYSTEM_CA = '1'
npm ci
```

Isso mantém a verificação HTTPS ativa. O backend compartilha os certificados
confiáveis do Windows com a biblioteca de rede automaticamente.

## Como usar

1. Abra o Clipa com `npm start`.
2. Cole o link de um vídeo, Short, Reel ou publicação com vídeo.
3. Clique em **Buscar mídia** para conferir a prévia. Também é possível iniciar
   o download diretamente pelo link.
4. Escolha **Vídeo** ou **Áudio**, a qualidade e o formato.
5. Use **Alterar** para escolher a pasta de destino, se desejar.
6. Clique em **Baixar vídeo** ou **Baixar áudio**. Ao concluir, use **Abrir pasta**.

A resolução escolhida é um limite: o Clipa usa a melhor opção disponível até
esse valor. Alguns posts não informam resolução, então o arquivo disponível é
utilizado. Converter para FLAC ou WAV não recupera qualidade perdida na fonte.
Cancelar interrompe a transferência no próximo evento de progresso; a conversão
final já iniciada pelo FFmpeg termina normalmente. Arquivos parciais podem ficar
na pasta para permitir retomada numa nova tentativa.

## Instagram, X e TikTok

Esses serviços podem exigir autenticação, limitar requisições ou bloquear acesso
automatizado. O suporte depende do [yt-dlp](https://github.com/yt-dlp/yt-dlp), da
publicação, da região e da sessão. Não há garantia de que todo link público funcione.

O Clipa normaliza links compartilhados, aceita links curtos do TikTok, usa uma
alternativa de extração para o X e aceita posts sem informação de duração ou
resolução. O suporte de rede `curl-cffi` é instalado para os extratores que precisam
de compatibilidade com navegadores.

Se a mensagem pedir sessão:

1. Confirme no navegador que sua conta tem acesso à publicação.
2. Obtenha um arquivo de cookies no formato Netscape, conforme o
   [tutorial do yt-dlp](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp).
3. No Clipa, entre em **Configurações → Sessão das plataformas → Selecionar arquivo**.
4. Busque ou baixe o link novamente.

O Clipa não lê seus navegadores automaticamente nem armazena senhas. Guarda
apenas o caminho do arquivo selecionado. O arquivo original não é alterado; cada
operação usa uma cópia temporária privada. Cookies podem dar acesso à sua conta:
não compartilhe o arquivo nem faça commit dele. O `.gitignore` já exclui nomes
comuns de arquivos de sessão.

## Resolver problemas

| Mensagem ou situação                          | Como resolver                                                        |
| --------------------------------------------- | -------------------------------------------------------------------- |
| FFmpeg ausente                                | Instale FFmpeg e FFprobe, confirme que estão no PATH e reabra o app. |
| A plataforma exige sessão                     | Selecione um arquivo de cookies válido de uma conta com acesso.      |
| A plataforma bloqueou ou limitou tentativas   | Confira o link no navegador e aguarde antes de repetir.              |
| Publicação sem vídeo                          | Use o link de um vídeo; fotos e perfis não são suportados.           |
| Não foi possível gravar                       | Escolha uma pasta com permissão de escrita e espaço livre.           |
| Erro de certificado                           | Confira os certificados da sua rede; não desative HTTPS.             |
| Link que antes funcionava deixou de funcionar | Atualize o yt-dlp e tente novamente.                                 |

Atualizar as dependências de extração no Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade -r python/requirements.txt
```

No Windows, os logs ficam em `%LOCALAPPDATA%\Clipa\backend.log`. O Python da
Microsoft Store pode redirecionar esse caminho para o `LocalCache` do pacote.
Você pode definir `CLIPA_LOG_DIR` para escolher outra pasta. Os logs têm rotação
de tamanho e podem conter URLs: revise antes de compartilhá-los.

## Testes

```powershell
npm run check
npm run format:check
npm test
```

Os testes cobrem inicialização e encerramento do backend, autenticação local,
links das quatro plataformas, fallback do X, seleção de formatos sem resolução,
sessões, estados de download, cancelamento e validação de erros. Eles não
dependem de conexão com as plataformas nem de contas pessoais.

Para verificar um link real, sem baixar o arquivo:

```powershell
.\.venv\Scripts\python.exe scripts/smoke-platforms.py 'LINK_DA_PUBLICACAO'
```

Adicione `--download` para baixar um vídeo de teste de até 30 MB em
`.artifacts/smoke/`, ou `--cookies 'C:\caminho\cookies.txt'` para usar uma sessão
selecionada por você. Use apenas links que tenha permissão para baixar. Esses
testes podem falhar por indisponibilidade ou restrições externas, mesmo quando
os testes automatizados passam.

## Gerar instalador Windows

No Windows, com Node.js, FFmpeg e FFprobe no PATH:

```powershell
.\.venv\Scripts\python.exe -m pip install -r python/requirements-build.txt
npm run build:win
```

O comando executa testes, empacota o backend com PyInstaller, copia as ferramentas
locais e gera o instalador em `dist/`. O usuário do instalador não precisa
instalar Python, Node.js ou FFmpeg separadamente. Para empacotar apenas o backend:

```powershell
npm run build:backend
```

`npm run build:mac` e `npm run build:linux` devem ser executados no respectivo
sistema operacional. Os binários precisam corresponder à arquitetura de destino.
As configurações usam os ícones padrão do Electron até que ícones próprios sejam
adicionados. Assinatura digital e atualização automática ainda não estão configuradas.
Antes de distribuir binários, confira os avisos e as licenças das ferramentas
incluídas em [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Estrutura

```text
electron/       Janela, integração com o sistema e interface
python/         API local e integração com yt-dlp / FFmpeg
scripts/        Testes reais opcionais e empacotamento
tests/          Testes automatizados em JavaScript e Python
.github/        CI para Windows e Linux
```

A API escuta apenas em `127.0.0.1`, em uma porta atribuída pelo sistema. A janela
usa um token temporário por execução. O histórico e as preferências ficam no
armazenamento local do aplicativo. O Clipa não é um serviço web para expor na internet.

## Subir para o GitHub

O `.gitignore` exclui dependências, ambientes virtuais, builds, logs, sessões e
arquivos de mídia. `package-lock.json` deve ser versionado para instalações com
`npm ci`. Antes do primeiro envio, revise os arquivos:

```powershell
git status --short
git add .
git diff --cached --stat
git commit -m "Prepare Clipa desktop application"
```

Crie um repositório vazio no GitHub. Se ainda não houver `origin`, use o endereço
do seu repositório e envie a branch desejada:

```powershell
git remote add origin https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
git push -u origin HEAD
```

Publique instaladores em **GitHub Releases**, como anexos da versão, em vez de
versionar arquivos `.exe`. Veja também [CONTRIBUTING.md](CONTRIBUTING.md).

## Licença

[MIT](LICENSE), para o código do Clipa. Use o aplicativo somente com conteúdo que
você tem autorização para baixar e respeite os termos de cada plataforma.
