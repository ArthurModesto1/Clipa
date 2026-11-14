# Componentes de terceiros

O código do Clipa tem licença MIT. As dependências mantêm suas próprias licenças.

| Componente       | Projeto / licença                                                                 |
| ---------------- | --------------------------------------------------------------------------------- |
| Electron         | https://github.com/electron/electron — MIT e avisos do Chromium                   |
| Node.js          | https://github.com/nodejs/node/blob/main/LICENSE — MIT e componentes relacionados |
| Python           | https://docs.python.org/3/license.html — PSF                                      |
| Flask            | https://github.com/pallets/flask — BSD-3-Clause                                   |
| Flask-CORS       | https://github.com/corydolphin/flask-cors — MIT                                   |
| yt-dlp           | https://github.com/yt-dlp/yt-dlp — Unlicense; dependências com licenças próprias  |
| curl-cffi        | https://github.com/lexiforest/curl_cffi — MIT e componentes relacionados          |
| FFmpeg / FFprobe | https://ffmpeg.org/legal.html — depende da configuração dos binários usados       |

O script de build copia FFmpeg, FFprobe e Node.js do PATH local e registra suas
versões em `tools/versions.json`. Ele não baixa nem escolhe uma distribuição deles.
Ao distribuir instaladores, inclua os avisos e licenças dessas distribuições.
Consulte a origem e a configuração do FFmpeg utilizado antes de redistribuí-lo;
builds que habilitam componentes GPL têm exigências diferentes de builds LGPL.
O empacotador não substitui essa revisão da distribuição escolhida.
