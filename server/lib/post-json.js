'use strict';

const http = require('http');
const https = require('https');
const { URL } = require('url');

/**
 * 发送 POST JSON 请求，纯原生实现（不调用 shell/curl，避免命令注入）。
 * 支持通过 HTTP 代理走 CONNECT 隧道（替代 curl --proxy）。
 *
 * @param {string} targetUrl  目标地址，如 https://open.bigmodel.cn/...
 * @param {object} headers    请求头（Content-Length 会自动补全）
 * @param {string} body       已序列化的 JSON 字符串
 * @param {object} [opts]
 * @param {string|null} [opts.proxy]    代理地址，如 http://127.0.0.1:7897；null 表示直连
 * @param {number} [opts.timeoutMs]     超时毫秒，默认 35000
 * @returns {Promise<string>} 响应体原始字符串
 */
function postJson(targetUrl, headers, body, opts = {}) {
  const { proxy = null, timeoutMs = 35000 } = opts;
  return new Promise((resolve, reject) => {
    let target;
    try {
      target = new URL(targetUrl);
    } catch (e) {
      return reject(new Error('非法的目标地址: ' + targetUrl));
    }
    const isHttps = target.protocol === 'https:';
    const port = target.port ? Number(target.port) : (isHttps ? 443 : 80);
    const reqHeaders = Object.assign({}, headers, {
      'Content-Length': Buffer.byteLength(body),
    });

    const onResponse = (res) => {
      let data = '';
      res.setEncoding('utf-8');
      res.on('data', (c) => { data += c; });
      res.on('end', () => resolve(data));
    };

    const sendRequest = (socket) => {
      const lib = isHttps ? https : http;
      const reqOpts = {
        method: 'POST',
        hostname: target.hostname,
        port,
        path: target.pathname + target.search,
        headers: reqHeaders,
      };
      if (socket) {
        reqOpts.socket = socket;
        reqOpts.agent = false;
      }
      const req = lib.request(reqOpts, onResponse);
      req.on('error', reject);
      req.setTimeout(timeoutMs, () => req.destroy(new Error('请求超时')));
      req.write(body);
      req.end();
    };

    if (proxy) {
      let proxyUrl;
      try {
        proxyUrl = new URL(proxy);
      } catch (e) {
        return reject(new Error('非法的代理地址: ' + proxy));
      }
      const connectReq = http.request({
        host: proxyUrl.hostname,
        port: proxyUrl.port ? Number(proxyUrl.port) : 80,
        method: 'CONNECT',
        path: `${target.hostname}:${port}`,
      });
      connectReq.on('connect', (res, socket) => {
        if (res.statusCode !== 200) {
          socket.destroy();
          return reject(new Error('代理 CONNECT 失败: ' + res.statusCode));
        }
        sendRequest(socket);
      });
      connectReq.on('error', reject);
      connectReq.setTimeout(timeoutMs, () => connectReq.destroy(new Error('代理连接超时')));
      connectReq.end();
    } else {
      sendRequest(null);
    }
  });
}

module.exports = { postJson };
