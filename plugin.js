/**
 * 连接手机 / Phone Remote — 扫码在手机上继续对话
 * ---------------------------------------------------------------------------
 * 目的：把「手机远程聊天」做成桌面版内置入口 —— 手机浏览器扫码即可继续对话。
 * 底层零自研：直接复用 Hermes 自带 dashboard（手机浏览器打开 http://<LAN-IP>:9119/），
 * 本插件只负责：① 出二维码 ② 给地址/账号/密码 ③ 一键打开本机面板 ④ 探测 IP 与服务状态。
 *
 * 入口三处：
 *   · Ctrl/⌘+K 搜「连接手机」（PALETTE_AREA）
 *   · 左侧栏导航「连接手机」（SIDEBAR_NAV_AREA）
 *   · 页面路由 /phone-connect（ROUTES_AREA）
 *
 * 注意：插件运行在受限沙箱里，只能 import '@hermes/plugin-sdk' / 'react' /
 * 'react/jsx-runtime'，且没有 JSX 编译 —— 所有元素都写成 jsx()/jsxs() 调用。
 * ctx.os 只开放 notify / openExternal / revealPath / writeClipboard，
 * 拿不到 shell，起服务那步只能靠外面的启动脚本（本页给按钮复制路径）。
 */
import {
  PALETTE_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  atom,
  Button,
  Input,
  Separator,
  host,
  useValue
} from '@hermes/plugin-sdk'
import { useEffect, useMemo, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

/* ─── 内联二维码编码器 ───────────────────────────────────────────────────────
   qrcode-generator v2.0.4 · MIT · (c) Kazuhiko Arase
   因为插件不能引外部 npm 包，这里把库源码内联（UMD 用伪 exports 包一层，
   使卷绕后的 factory 走 CommonJS 分支把构造函数交给 module.exports）。
   已验证：生成矩阵用 OpenCV 实扫，能解回原始 URL。
   ──────────────────────────────────────────────────────────────────────── */
const makeQr = (function () {
  const module = { exports: {} }
  const exports = module.exports
//---------------------------------------------------------------------
//
// QR Code Generator for JavaScript
//
// Copyright (c) 2009 Kazuhiko Arase
//
// URL: http://www.d-project.com/
//
// Licensed under the MIT license:
//  http://www.opensource.org/licenses/mit-license.php
//
// The word 'QR Code' is registered trademark of
// DENSO WAVE INCORPORATED
//  http://www.denso-wave.com/qrcode/faqpatent-e.html
//
//---------------------------------------------------------------------

var qrcode = function() {

  //---------------------------------------------------------------------
  // qrcode
  //---------------------------------------------------------------------

  /**
   * qrcode
   * @param typeNumber 1 to 40
   * @param errorCorrectionLevel 'L','M','Q','H'
   */
  var qrcode = function(typeNumber, errorCorrectionLevel) {

    var PAD0 = 0xEC;
    var PAD1 = 0x11;

    var _typeNumber = typeNumber;
    var _errorCorrectionLevel = QRErrorCorrectionLevel[errorCorrectionLevel];
    var _modules = null;
    var _moduleCount = 0;
    var _dataCache = null;
    var _dataList = [];

    var _this = {};

    var makeImpl = function(test, maskPattern) {

      _moduleCount = _typeNumber * 4 + 17;
      _modules = function(moduleCount) {
        var modules = new Array(moduleCount);
        for (var row = 0; row < moduleCount; row += 1) {
          modules[row] = new Array(moduleCount);
          for (var col = 0; col < moduleCount; col += 1) {
            modules[row][col] = null;
          }
        }
        return modules;
      }(_moduleCount);

      setupPositionProbePattern(0, 0);
      setupPositionProbePattern(_moduleCount - 7, 0);
      setupPositionProbePattern(0, _moduleCount - 7);
      setupPositionAdjustPattern();
      setupTimingPattern();
      setupTypeInfo(test, maskPattern);

      if (_typeNumber >= 7) {
        setupTypeNumber(test);
      }

      if (_dataCache == null) {
        _dataCache = createData(_typeNumber, _errorCorrectionLevel, _dataList);
      }

      mapData(_dataCache, maskPattern);
    };

    var setupPositionProbePattern = function(row, col) {

      for (var r = -1; r <= 7; r += 1) {

        if (row + r <= -1 || _moduleCount <= row + r) continue;

        for (var c = -1; c <= 7; c += 1) {

          if (col + c <= -1 || _moduleCount <= col + c) continue;

          if ( (0 <= r && r <= 6 && (c == 0 || c == 6) )
              || (0 <= c && c <= 6 && (r == 0 || r == 6) )
              || (2 <= r && r <= 4 && 2 <= c && c <= 4) ) {
            _modules[row + r][col + c] = true;
          } else {
            _modules[row + r][col + c] = false;
          }
        }
      }
    };

    var getBestMaskPattern = function() {

      var minLostPoint = 0;
      var pattern = 0;

      for (var i = 0; i < 8; i += 1) {

        makeImpl(true, i);

        var lostPoint = QRUtil.getLostPoint(_this);

        if (i == 0 || minLostPoint > lostPoint) {
          minLostPoint = lostPoint;
          pattern = i;
        }
      }

      return pattern;
    };

    var setupTimingPattern = function() {

      for (var r = 8; r < _moduleCount - 8; r += 1) {
        if (_modules[r][6] != null) {
          continue;
        }
        _modules[r][6] = (r % 2 == 0);
      }

      for (var c = 8; c < _moduleCount - 8; c += 1) {
        if (_modules[6][c] != null) {
          continue;
        }
        _modules[6][c] = (c % 2 == 0);
      }
    };

    var setupPositionAdjustPattern = function() {

      var pos = QRUtil.getPatternPosition(_typeNumber);

      for (var i = 0; i < pos.length; i += 1) {

        for (var j = 0; j < pos.length; j += 1) {

          var row = pos[i];
          var col = pos[j];

          if (_modules[row][col] != null) {
            continue;
          }

          for (var r = -2; r <= 2; r += 1) {

            for (var c = -2; c <= 2; c += 1) {

              if (r == -2 || r == 2 || c == -2 || c == 2
                  || (r == 0 && c == 0) ) {
                _modules[row + r][col + c] = true;
              } else {
                _modules[row + r][col + c] = false;
              }
            }
          }
        }
      }
    };

    var setupTypeNumber = function(test) {

      var bits = QRUtil.getBCHTypeNumber(_typeNumber);

      for (var i = 0; i < 18; i += 1) {
        var mod = (!test && ( (bits >> i) & 1) == 1);
        _modules[Math.floor(i / 3)][i % 3 + _moduleCount - 8 - 3] = mod;
      }

      for (var i = 0; i < 18; i += 1) {
        var mod = (!test && ( (bits >> i) & 1) == 1);
        _modules[i % 3 + _moduleCount - 8 - 3][Math.floor(i / 3)] = mod;
      }
    };

    var setupTypeInfo = function(test, maskPattern) {

      var data = (_errorCorrectionLevel << 3) | maskPattern;
      var bits = QRUtil.getBCHTypeInfo(data);

      // vertical
      for (var i = 0; i < 15; i += 1) {

        var mod = (!test && ( (bits >> i) & 1) == 1);

        if (i < 6) {
          _modules[i][8] = mod;
        } else if (i < 8) {
          _modules[i + 1][8] = mod;
        } else {
          _modules[_moduleCount - 15 + i][8] = mod;
        }
      }

      // horizontal
      for (var i = 0; i < 15; i += 1) {

        var mod = (!test && ( (bits >> i) & 1) == 1);

        if (i < 8) {
          _modules[8][_moduleCount - i - 1] = mod;
        } else if (i < 9) {
          _modules[8][15 - i - 1 + 1] = mod;
        } else {
          _modules[8][15 - i - 1] = mod;
        }
      }

      // fixed module
      _modules[_moduleCount - 8][8] = (!test);
    };

    var mapData = function(data, maskPattern) {

      var inc = -1;
      var row = _moduleCount - 1;
      var bitIndex = 7;
      var byteIndex = 0;
      var maskFunc = QRUtil.getMaskFunction(maskPattern);

      for (var col = _moduleCount - 1; col > 0; col -= 2) {

        if (col == 6) col -= 1;

        while (true) {

          for (var c = 0; c < 2; c += 1) {

            if (_modules[row][col - c] == null) {

              var dark = false;

              if (byteIndex < data.length) {
                dark = ( ( (data[byteIndex] >>> bitIndex) & 1) == 1);
              }

              var mask = maskFunc(row, col - c);

              if (mask) {
                dark = !dark;
              }

              _modules[row][col - c] = dark;
              bitIndex -= 1;

              if (bitIndex == -1) {
                byteIndex += 1;
                bitIndex = 7;
              }
            }
          }

          row += inc;

          if (row < 0 || _moduleCount <= row) {
            row -= inc;
            inc = -inc;
            break;
          }
        }
      }
    };

    var createBytes = function(buffer, rsBlocks) {

      var offset = 0;

      var maxDcCount = 0;
      var maxEcCount = 0;

      var dcdata = new Array(rsBlocks.length);
      var ecdata = new Array(rsBlocks.length);

      for (var r = 0; r < rsBlocks.length; r += 1) {

        var dcCount = rsBlocks[r].dataCount;
        var ecCount = rsBlocks[r].totalCount - dcCount;

        maxDcCount = Math.max(maxDcCount, dcCount);
        maxEcCount = Math.max(maxEcCount, ecCount);

        dcdata[r] = new Array(dcCount);

        for (var i = 0; i < dcdata[r].length; i += 1) {
          dcdata[r][i] = 0xff & buffer.getBuffer()[i + offset];
        }
        offset += dcCount;

        var rsPoly = QRUtil.getErrorCorrectPolynomial(ecCount);
        var rawPoly = qrPolynomial(dcdata[r], rsPoly.getLength() - 1);

        var modPoly = rawPoly.mod(rsPoly);
        ecdata[r] = new Array(rsPoly.getLength() - 1);
        for (var i = 0; i < ecdata[r].length; i += 1) {
          var modIndex = i + modPoly.getLength() - ecdata[r].length;
          ecdata[r][i] = (modIndex >= 0)? modPoly.getAt(modIndex) : 0;
        }
      }

      var totalCodeCount = 0;
      for (var i = 0; i < rsBlocks.length; i += 1) {
        totalCodeCount += rsBlocks[i].totalCount;
      }

      var data = new Array(totalCodeCount);
      var index = 0;

      for (var i = 0; i < maxDcCount; i += 1) {
        for (var r = 0; r < rsBlocks.length; r += 1) {
          if (i < dcdata[r].length) {
            data[index] = dcdata[r][i];
            index += 1;
          }
        }
      }

      for (var i = 0; i < maxEcCount; i += 1) {
        for (var r = 0; r < rsBlocks.length; r += 1) {
          if (i < ecdata[r].length) {
            data[index] = ecdata[r][i];
            index += 1;
          }
        }
      }

      return data;
    };

    var createData = function(typeNumber, errorCorrectionLevel, dataList) {

      var rsBlocks = QRRSBlock.getRSBlocks(typeNumber, errorCorrectionLevel);

      var buffer = qrBitBuffer();

      for (var i = 0; i < dataList.length; i += 1) {
        var data = dataList[i];
        buffer.put(data.getMode(), 4);
        buffer.put(data.getLength(), QRUtil.getLengthInBits(data.getMode(), typeNumber) );
        data.write(buffer);
      }

      // calc num max data.
      var totalDataCount = 0;
      for (var i = 0; i < rsBlocks.length; i += 1) {
        totalDataCount += rsBlocks[i].dataCount;
      }

      if (buffer.getLengthInBits() > totalDataCount * 8) {
        throw 'code length overflow. ('
          + buffer.getLengthInBits()
          + '>'
          + totalDataCount * 8
          + ')';
      }

      // end code
      if (buffer.getLengthInBits() + 4 <= totalDataCount * 8) {
        buffer.put(0, 4);
      }

      // padding
      while (buffer.getLengthInBits() % 8 != 0) {
        buffer.putBit(false);
      }

      // padding
      while (true) {

        if (buffer.getLengthInBits() >= totalDataCount * 8) {
          break;
        }
        buffer.put(PAD0, 8);

        if (buffer.getLengthInBits() >= totalDataCount * 8) {
          break;
        }
        buffer.put(PAD1, 8);
      }

      return createBytes(buffer, rsBlocks);
    };

    _this.addData = function(data, mode) {

      mode = mode || 'Byte';

      var newData = null;

      switch(mode) {
      case 'Numeric' :
        newData = qrNumber(data);
        break;
      case 'Alphanumeric' :
        newData = qrAlphaNum(data);
        break;
      case 'Byte' :
        newData = qr8BitByte(data);
        break;
      case 'Kanji' :
        newData = qrKanji(data);
        break;
      default :
        throw 'mode:' + mode;
      }

      _dataList.push(newData);
      _dataCache = null;
    };

    _this.isDark = function(row, col) {
      if (row < 0 || _moduleCount <= row || col < 0 || _moduleCount <= col) {
        throw row + ',' + col;
      }
      return _modules[row][col];
    };

    _this.getModuleCount = function() {
      return _moduleCount;
    };

    _this.make = function() {
      if (_typeNumber < 1) {
        var typeNumber = 1;

        for (; typeNumber < 40; typeNumber++) {
          var rsBlocks = QRRSBlock.getRSBlocks(typeNumber, _errorCorrectionLevel);
          var buffer = qrBitBuffer();

          for (var i = 0; i < _dataList.length; i++) {
            var data = _dataList[i];
            buffer.put(data.getMode(), 4);
            buffer.put(data.getLength(), QRUtil.getLengthInBits(data.getMode(), typeNumber) );
            data.write(buffer);
          }

          var totalDataCount = 0;
          for (var i = 0; i < rsBlocks.length; i++) {
            totalDataCount += rsBlocks[i].dataCount;
          }

          if (buffer.getLengthInBits() <= totalDataCount * 8) {
            break;
          }
        }

        _typeNumber = typeNumber;
      }

      makeImpl(false, getBestMaskPattern() );
    };

    _this.createTableTag = function(cellSize, margin) {

      cellSize = cellSize || 2;
      margin = (typeof margin == 'undefined')? cellSize * 4 : margin;

      var qrHtml = '';

      qrHtml += '<table style="';
      qrHtml += ' border-width: 0px; border-style: none;';
      qrHtml += ' border-collapse: collapse;';
      qrHtml += ' padding: 0px; margin: ' + margin + 'px;';
      qrHtml += '">';
      qrHtml += '<tbody>';

      for (var r = 0; r < _this.getModuleCount(); r += 1) {

        qrHtml += '<tr>';

        for (var c = 0; c < _this.getModuleCount(); c += 1) {
          qrHtml += '<td style="';
          qrHtml += ' border-width: 0px; border-style: none;';
          qrHtml += ' border-collapse: collapse;';
          qrHtml += ' padding: 0px; margin: 0px;';
          qrHtml += ' width: ' + cellSize + 'px;';
          qrHtml += ' height: ' + cellSize + 'px;';
          qrHtml += ' background-color: ';
          qrHtml += _this.isDark(r, c)? '#000000' : '#ffffff';
          qrHtml += ';';
          qrHtml += '"/>';
        }

        qrHtml += '</tr>';
      }

      qrHtml += '</tbody>';
      qrHtml += '</table>';

      return qrHtml;
    };

    _this.createSvgTag = function(cellSize, margin, alt, title) {

      var opts = {};
      if (typeof arguments[0] == 'object') {
        // Called by options.
        opts = arguments[0];
        // overwrite cellSize and margin.
        cellSize = opts.cellSize;
        margin = opts.margin;
        alt = opts.alt;
        title = opts.title;
      }

      cellSize = cellSize || 2;
      margin = (typeof margin == 'undefined')? cellSize * 4 : margin;

      // Compose alt property surrogate
      alt = (typeof alt === 'string') ? {text: alt} : alt || {};
      alt.text = alt.text || null;
      alt.id = (alt.text) ? alt.id || 'qrcode-description' : null;

      // Compose title property surrogate
      title = (typeof title === 'string') ? {text: title} : title || {};
      title.text = title.text || null;
      title.id = (title.text) ? title.id || 'qrcode-title' : null;

      var size = _this.getModuleCount() * cellSize + margin * 2;
      var c, mc, r, mr, qrSvg='', rect;

      rect = 'l' + cellSize + ',0 0,' + cellSize +
        ' -' + cellSize + ',0 0,-' + cellSize + 'z ';

      qrSvg += '<svg version="1.1" xmlns="http://www.w3.org/2000/svg"';
      qrSvg += !opts.scalable ? ' width="' + size + 'px" height="' + size + 'px"' : '';
      qrSvg += ' viewBox="0 0 ' + size + ' ' + size + '" ';
      qrSvg += ' preserveAspectRatio="xMinYMin meet"';
      qrSvg += (title.text || alt.text) ? ' role="img" aria-labelledby="' +
          escapeXml([title.id, alt.id].join(' ').trim() ) + '"' : '';
      qrSvg += '>';
      qrSvg += (title.text) ? '<title id="' + escapeXml(title.id) + '">' +
          escapeXml(title.text) + '</title>' : '';
      qrSvg += (alt.text) ? '<description id="' + escapeXml(alt.id) + '">' +
          escapeXml(alt.text) + '</description>' : '';
      qrSvg += '<rect width="100%" height="100%" fill="white" cx="0" cy="0"/>';
      qrSvg += '<path d="';

      for (r = 0; r < _this.getModuleCount(); r += 1) {
        mr = r * cellSize + margin;
        for (c = 0; c < _this.getModuleCount(); c += 1) {
          if (_this.isDark(r, c) ) {
            mc = c*cellSize+margin;
            qrSvg += 'M' + mc + ',' + mr + rect;
          }
        }
      }

      qrSvg += '" stroke="transparent" fill="black"/>';
      qrSvg += '</svg>';

      return qrSvg;
    };

    _this.createDataURL = function(cellSize, margin) {

      cellSize = cellSize || 2;
      margin = (typeof margin == 'undefined')? cellSize * 4 : margin;

      var size = _this.getModuleCount() * cellSize + margin * 2;
      var min = margin;
      var max = size - margin;

      return createDataURL(size, size, function(x, y) {
        if (min <= x && x < max && min <= y && y < max) {
          var c = Math.floor( (x - min) / cellSize);
          var r = Math.floor( (y - min) / cellSize);
          return _this.isDark(r, c)? 0 : 1;
        } else {
          return 1;
        }
      } );
    };

    _this.createImgTag = function(cellSize, margin, alt) {

      cellSize = cellSize || 2;
      margin = (typeof margin == 'undefined')? cellSize * 4 : margin;

      var size = _this.getModuleCount() * cellSize + margin * 2;

      var img = '';
      img += '<img';
      img += '\u0020src="';
      img += _this.createDataURL(cellSize, margin);
      img += '"';
      img += '\u0020width="';
      img += size;
      img += '"';
      img += '\u0020height="';
      img += size;
      img += '"';
      if (alt) {
        img += '\u0020alt="';
        img += escapeXml(alt);
        img += '"';
      }
      img += '/>';

      return img;
    };

    var escapeXml = function(s) {
      var escaped = '';
      for (var i = 0; i < s.length; i += 1) {
        var c = s.charAt(i);
        switch(c) {
        case '<': escaped += '&lt;'; break;
        case '>': escaped += '&gt;'; break;
        case '&': escaped += '&amp;'; break;
        case '"': escaped += '&quot;'; break;
        default : escaped += c; break;
        }
      }
      return escaped;
    };

    var _createHalfASCII = function(margin) {
      var cellSize = 1;
      margin = (typeof margin == 'undefined')? cellSize * 2 : margin;

      var size = _this.getModuleCount() * cellSize + margin * 2;
      var min = margin;
      var max = size - margin;

      var y, x, r1, r2, p;

      var blocks = {
        '██': '█',
        '█ ': '▀',
        ' █': '▄',
        '  ': ' '
      };

      var blocksLastLineNoMargin = {
        '██': '▀',
        '█ ': '▀',
        ' █': ' ',
        '  ': ' '
      };

      var ascii = '';
      for (y = 0; y < size; y += 2) {
        r1 = Math.floor((y - min) / cellSize);
        r2 = Math.floor((y + 1 - min) / cellSize);
        for (x = 0; x < size; x += 1) {
          p = '█';

          if (min <= x && x < max && min <= y && y < max && _this.isDark(r1, Math.floor((x - min) / cellSize))) {
            p = ' ';
          }

          if (min <= x && x < max && min <= y+1 && y+1 < max && _this.isDark(r2, Math.floor((x - min) / cellSize))) {
            p += ' ';
          }
          else {
            p += '█';
          }

          // Output 2 characters per pixel, to create full square. 1 character per pixels gives only half width of square.
          ascii += (margin < 1 && y+1 >= max) ? blocksLastLineNoMargin[p] : blocks[p];
        }

        ascii += '\n';
      }

      if (size % 2 && margin > 0) {
        return ascii.substring(0, ascii.length - size - 1) + Array(size+1).join('▀');
      }

      return ascii.substring(0, ascii.length-1);
    };

    _this.createASCII = function(cellSize, margin) {
      cellSize = cellSize || 1;

      if (cellSize < 2) {
        return _createHalfASCII(margin);
      }

      cellSize -= 1;
      margin = (typeof margin == 'undefined')? cellSize * 2 : margin;

      var size = _this.getModuleCount() * cellSize + margin * 2;
      var min = margin;
      var max = size - margin;

      var y, x, r, p;

      var white = Array(cellSize+1).join('██');
      var black = Array(cellSize+1).join('  ');

      var ascii = '';
      var line = '';
      for (y = 0; y < size; y += 1) {
        r = Math.floor( (y - min) / cellSize);
        line = '';
        for (x = 0; x < size; x += 1) {
          p = 1;

          if (min <= x && x < max && min <= y && y < max && _this.isDark(r, Math.floor((x - min) / cellSize))) {
            p = 0;
          }

          // Output 2 characters per pixel, to create full square. 1 character per pixels gives only half width of square.
          line += p ? white : black;
        }

        for (r = 0; r < cellSize; r += 1) {
          ascii += line + '\n';
        }
      }

      return ascii.substring(0, ascii.length-1);
    };

    _this.renderTo2dContext = function(context, cellSize) {
      cellSize = cellSize || 2;
      var length = _this.getModuleCount();
      for (var row = 0; row < length; row++) {
        for (var col = 0; col < length; col++) {
          context.fillStyle = _this.isDark(row, col) ? 'black' : 'white';
          context.fillRect(col * cellSize, row * cellSize, cellSize, cellSize);
        }
      }
    }

    return _this;
  };

  //---------------------------------------------------------------------
  // qrcode.stringToBytes
  //---------------------------------------------------------------------

  qrcode.stringToBytesFuncs = {
    'default' : function(s) {
      var bytes = [];
      for (var i = 0; i < s.length; i += 1) {
        var c = s.charCodeAt(i);
        bytes.push(c & 0xff);
      }
      return bytes;
    }
  };

  qrcode.stringToBytes = qrcode.stringToBytesFuncs['default'];

  //---------------------------------------------------------------------
  // qrcode.createStringToBytes
  //---------------------------------------------------------------------

  /**
   * @param unicodeData base64 string of byte array.
   * [16bit Unicode],[16bit Bytes], ...
   * @param numChars
   */
  qrcode.createStringToBytes = function(unicodeData, numChars) {

    // create conversion map.

    var unicodeMap = function() {

      var bin = base64DecodeInputStream(unicodeData);
      var read = function() {
        var b = bin.read();
        if (b == -1) throw 'eof';
        return b;
      };

      var count = 0;
      var unicodeMap = {};
      while (true) {
        var b0 = bin.read();
        if (b0 == -1) break;
        var b1 = read();
        var b2 = read();
        var b3 = read();
        var k = String.fromCharCode( (b0 << 8) | b1);
        var v = (b2 << 8) | b3;
        unicodeMap[k] = v;
        count += 1;
      }
      if (count != numChars) {
        throw count + ' != ' + numChars;
      }

      return unicodeMap;
    }();

    var unknownChar = '?'.charCodeAt(0);

    return function(s) {
      var bytes = [];
      for (var i = 0; i < s.length; i += 1) {
        var c = s.charCodeAt(i);
        if (c < 128) {
          bytes.push(c);
        } else {
          var b = unicodeMap[s.charAt(i)];
          if (typeof b == 'number') {
            if ( (b & 0xff) == b) {
              // 1byte
              bytes.push(b);
            } else {
              // 2bytes
              bytes.push(b >>> 8);
              bytes.push(b & 0xff);
            }
          } else {
            bytes.push(unknownChar);
          }
        }
      }
      return bytes;
    };
  };

  //---------------------------------------------------------------------
  // QRMode
  //---------------------------------------------------------------------

  var QRMode = {
    MODE_NUMBER :    1 << 0,
    MODE_ALPHA_NUM : 1 << 1,
    MODE_8BIT_BYTE : 1 << 2,
    MODE_KANJI :     1 << 3
  };

  //---------------------------------------------------------------------
  // QRErrorCorrectionLevel
  //---------------------------------------------------------------------

  var QRErrorCorrectionLevel = {
    L : 1,
    M : 0,
    Q : 3,
    H : 2
  };

  //---------------------------------------------------------------------
  // QRMaskPattern
  //---------------------------------------------------------------------

  var QRMaskPattern = {
    PATTERN000 : 0,
    PATTERN001 : 1,
    PATTERN010 : 2,
    PATTERN011 : 3,
    PATTERN100 : 4,
    PATTERN101 : 5,
    PATTERN110 : 6,
    PATTERN111 : 7
  };

  //---------------------------------------------------------------------
  // QRUtil
  //---------------------------------------------------------------------

  var QRUtil = function() {

    var PATTERN_POSITION_TABLE = [
      [],
      [6, 18],
      [6, 22],
      [6, 26],
      [6, 30],
      [6, 34],
      [6, 22, 38],
      [6, 24, 42],
      [6, 26, 46],
      [6, 28, 50],
      [6, 30, 54],
      [6, 32, 58],
      [6, 34, 62],
      [6, 26, 46, 66],
      [6, 26, 48, 70],
      [6, 26, 50, 74],
      [6, 30, 54, 78],
      [6, 30, 56, 82],
      [6, 30, 58, 86],
      [6, 34, 62, 90],
      [6, 28, 50, 72, 94],
      [6, 26, 50, 74, 98],
      [6, 30, 54, 78, 102],
      [6, 28, 54, 80, 106],
      [6, 32, 58, 84, 110],
      [6, 30, 58, 86, 114],
      [6, 34, 62, 90, 118],
      [6, 26, 50, 74, 98, 122],
      [6, 30, 54, 78, 102, 126],
      [6, 26, 52, 78, 104, 130],
      [6, 30, 56, 82, 108, 134],
      [6, 34, 60, 86, 112, 138],
      [6, 30, 58, 86, 114, 142],
      [6, 34, 62, 90, 118, 146],
      [6, 30, 54, 78, 102, 126, 150],
      [6, 24, 50, 76, 102, 128, 154],
      [6, 28, 54, 80, 106, 132, 158],
      [6, 32, 58, 84, 110, 136, 162],
      [6, 26, 54, 82, 110, 138, 166],
      [6, 30, 58, 86, 114, 142, 170]
    ];
    var G15 = (1 << 10) | (1 << 8) | (1 << 5) | (1 << 4) | (1 << 2) | (1 << 1) | (1 << 0);
    var G18 = (1 << 12) | (1 << 11) | (1 << 10) | (1 << 9) | (1 << 8) | (1 << 5) | (1 << 2) | (1 << 0);
    var G15_MASK = (1 << 14) | (1 << 12) | (1 << 10) | (1 << 4) | (1 << 1);

    var _this = {};

    var getBCHDigit = function(data) {
      var digit = 0;
      while (data != 0) {
        digit += 1;
        data >>>= 1;
      }
      return digit;
    };

    _this.getBCHTypeInfo = function(data) {
      var d = data << 10;
      while (getBCHDigit(d) - getBCHDigit(G15) >= 0) {
        d ^= (G15 << (getBCHDigit(d) - getBCHDigit(G15) ) );
      }
      return ( (data << 10) | d) ^ G15_MASK;
    };

    _this.getBCHTypeNumber = function(data) {
      var d = data << 12;
      while (getBCHDigit(d) - getBCHDigit(G18) >= 0) {
        d ^= (G18 << (getBCHDigit(d) - getBCHDigit(G18) ) );
      }
      return (data << 12) | d;
    };

    _this.getPatternPosition = function(typeNumber) {
      return PATTERN_POSITION_TABLE[typeNumber - 1];
    };

    _this.getMaskFunction = function(maskPattern) {

      switch (maskPattern) {

      case QRMaskPattern.PATTERN000 :
        return function(i, j) { return (i + j) % 2 == 0; };
      case QRMaskPattern.PATTERN001 :
        return function(i, j) { return i % 2 == 0; };
      case QRMaskPattern.PATTERN010 :
        return function(i, j) { return j % 3 == 0; };
      case QRMaskPattern.PATTERN011 :
        return function(i, j) { return (i + j) % 3 == 0; };
      case QRMaskPattern.PATTERN100 :
        return function(i, j) { return (Math.floor(i / 2) + Math.floor(j / 3) ) % 2 == 0; };
      case QRMaskPattern.PATTERN101 :
        return function(i, j) { return (i * j) % 2 + (i * j) % 3 == 0; };
      case QRMaskPattern.PATTERN110 :
        return function(i, j) { return ( (i * j) % 2 + (i * j) % 3) % 2 == 0; };
      case QRMaskPattern.PATTERN111 :
        return function(i, j) { return ( (i * j) % 3 + (i + j) % 2) % 2 == 0; };

      default :
        throw 'bad maskPattern:' + maskPattern;
      }
    };

    _this.getErrorCorrectPolynomial = function(errorCorrectLength) {
      var a = qrPolynomial([1], 0);
      for (var i = 0; i < errorCorrectLength; i += 1) {
        a = a.multiply(qrPolynomial([1, QRMath.gexp(i)], 0) );
      }
      return a;
    };

    _this.getLengthInBits = function(mode, type) {

      if (1 <= type && type < 10) {

        // 1 - 9

        switch(mode) {
        case QRMode.MODE_NUMBER    : return 10;
        case QRMode.MODE_ALPHA_NUM : return 9;
        case QRMode.MODE_8BIT_BYTE : return 8;
        case QRMode.MODE_KANJI     : return 8;
        default :
          throw 'mode:' + mode;
        }

      } else if (type < 27) {

        // 10 - 26

        switch(mode) {
        case QRMode.MODE_NUMBER    : return 12;
        case QRMode.MODE_ALPHA_NUM : return 11;
        case QRMode.MODE_8BIT_BYTE : return 16;
        case QRMode.MODE_KANJI     : return 10;
        default :
          throw 'mode:' + mode;
        }

      } else if (type < 41) {

        // 27 - 40

        switch(mode) {
        case QRMode.MODE_NUMBER    : return 14;
        case QRMode.MODE_ALPHA_NUM : return 13;
        case QRMode.MODE_8BIT_BYTE : return 16;
        case QRMode.MODE_KANJI     : return 12;
        default :
          throw 'mode:' + mode;
        }

      } else {
        throw 'type:' + type;
      }
    };

    _this.getLostPoint = function(qrcode) {

      var moduleCount = qrcode.getModuleCount();

      var lostPoint = 0;

      // LEVEL1

      for (var row = 0; row < moduleCount; row += 1) {
        for (var col = 0; col < moduleCount; col += 1) {

          var sameCount = 0;
          var dark = qrcode.isDark(row, col);

          for (var r = -1; r <= 1; r += 1) {

            if (row + r < 0 || moduleCount <= row + r) {
              continue;
            }

            for (var c = -1; c <= 1; c += 1) {

              if (col + c < 0 || moduleCount <= col + c) {
                continue;
              }

              if (r == 0 && c == 0) {
                continue;
              }

              if (dark == qrcode.isDark(row + r, col + c) ) {
                sameCount += 1;
              }
            }
          }

          if (sameCount > 5) {
            lostPoint += (3 + sameCount - 5);
          }
        }
      };

      // LEVEL2

      for (var row = 0; row < moduleCount - 1; row += 1) {
        for (var col = 0; col < moduleCount - 1; col += 1) {
          var count = 0;
          if (qrcode.isDark(row, col) ) count += 1;
          if (qrcode.isDark(row + 1, col) ) count += 1;
          if (qrcode.isDark(row, col + 1) ) count += 1;
          if (qrcode.isDark(row + 1, col + 1) ) count += 1;
          if (count == 0 || count == 4) {
            lostPoint += 3;
          }
        }
      }

      // LEVEL3

      for (var row = 0; row < moduleCount; row += 1) {
        for (var col = 0; col < moduleCount - 6; col += 1) {
          if (qrcode.isDark(row, col)
              && !qrcode.isDark(row, col + 1)
              &&  qrcode.isDark(row, col + 2)
              &&  qrcode.isDark(row, col + 3)
              &&  qrcode.isDark(row, col + 4)
              && !qrcode.isDark(row, col + 5)
              &&  qrcode.isDark(row, col + 6) ) {
            lostPoint += 40;
          }
        }
      }

      for (var col = 0; col < moduleCount; col += 1) {
        for (var row = 0; row < moduleCount - 6; row += 1) {
          if (qrcode.isDark(row, col)
              && !qrcode.isDark(row + 1, col)
              &&  qrcode.isDark(row + 2, col)
              &&  qrcode.isDark(row + 3, col)
              &&  qrcode.isDark(row + 4, col)
              && !qrcode.isDark(row + 5, col)
              &&  qrcode.isDark(row + 6, col) ) {
            lostPoint += 40;
          }
        }
      }

      // LEVEL4

      var darkCount = 0;

      for (var col = 0; col < moduleCount; col += 1) {
        for (var row = 0; row < moduleCount; row += 1) {
          if (qrcode.isDark(row, col) ) {
            darkCount += 1;
          }
        }
      }

      var ratio = Math.abs(100 * darkCount / moduleCount / moduleCount - 50) / 5;
      lostPoint += ratio * 10;

      return lostPoint;
    };

    return _this;
  }();

  //---------------------------------------------------------------------
  // QRMath
  //---------------------------------------------------------------------

  var QRMath = function() {

    var EXP_TABLE = new Array(256);
    var LOG_TABLE = new Array(256);

    // initialize tables
    for (var i = 0; i < 8; i += 1) {
      EXP_TABLE[i] = 1 << i;
    }
    for (var i = 8; i < 256; i += 1) {
      EXP_TABLE[i] = EXP_TABLE[i - 4]
        ^ EXP_TABLE[i - 5]
        ^ EXP_TABLE[i - 6]
        ^ EXP_TABLE[i - 8];
    }
    for (var i = 0; i < 255; i += 1) {
      LOG_TABLE[EXP_TABLE[i] ] = i;
    }

    var _this = {};

    _this.glog = function(n) {

      if (n < 1) {
        throw 'glog(' + n + ')';
      }

      return LOG_TABLE[n];
    };

    _this.gexp = function(n) {

      while (n < 0) {
        n += 255;
      }

      while (n >= 256) {
        n -= 255;
      }

      return EXP_TABLE[n];
    };

    return _this;
  }();

  //---------------------------------------------------------------------
  // qrPolynomial
  //---------------------------------------------------------------------

  function qrPolynomial(num, shift) {

    if (typeof num.length == 'undefined') {
      throw num.length + '/' + shift;
    }

    var _num = function() {
      var offset = 0;
      while (offset < num.length && num[offset] == 0) {
        offset += 1;
      }
      var _num = new Array(num.length - offset + shift);
      for (var i = 0; i < num.length - offset; i += 1) {
        _num[i] = num[i + offset];
      }
      return _num;
    }();

    var _this = {};

    _this.getAt = function(index) {
      return _num[index];
    };

    _this.getLength = function() {
      return _num.length;
    };

    _this.multiply = function(e) {

      var num = new Array(_this.getLength() + e.getLength() - 1);

      for (var i = 0; i < _this.getLength(); i += 1) {
        for (var j = 0; j < e.getLength(); j += 1) {
          num[i + j] ^= QRMath.gexp(QRMath.glog(_this.getAt(i) ) + QRMath.glog(e.getAt(j) ) );
        }
      }

      return qrPolynomial(num, 0);
    };

    _this.mod = function(e) {

      if (_this.getLength() - e.getLength() < 0) {
        return _this;
      }

      var ratio = QRMath.glog(_this.getAt(0) ) - QRMath.glog(e.getAt(0) );

      var num = new Array(_this.getLength() );
      for (var i = 0; i < _this.getLength(); i += 1) {
        num[i] = _this.getAt(i);
      }

      for (var i = 0; i < e.getLength(); i += 1) {
        num[i] ^= QRMath.gexp(QRMath.glog(e.getAt(i) ) + ratio);
      }

      // recursive call
      return qrPolynomial(num, 0).mod(e);
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // QRRSBlock
  //---------------------------------------------------------------------

  var QRRSBlock = function() {

    var RS_BLOCK_TABLE = [

      // L
      // M
      // Q
      // H

      // 1
      [1, 26, 19],
      [1, 26, 16],
      [1, 26, 13],
      [1, 26, 9],

      // 2
      [1, 44, 34],
      [1, 44, 28],
      [1, 44, 22],
      [1, 44, 16],

      // 3
      [1, 70, 55],
      [1, 70, 44],
      [2, 35, 17],
      [2, 35, 13],

      // 4
      [1, 100, 80],
      [2, 50, 32],
      [2, 50, 24],
      [4, 25, 9],

      // 5
      [1, 134, 108],
      [2, 67, 43],
      [2, 33, 15, 2, 34, 16],
      [2, 33, 11, 2, 34, 12],

      // 6
      [2, 86, 68],
      [4, 43, 27],
      [4, 43, 19],
      [4, 43, 15],

      // 7
      [2, 98, 78],
      [4, 49, 31],
      [2, 32, 14, 4, 33, 15],
      [4, 39, 13, 1, 40, 14],

      // 8
      [2, 121, 97],
      [2, 60, 38, 2, 61, 39],
      [4, 40, 18, 2, 41, 19],
      [4, 40, 14, 2, 41, 15],

      // 9
      [2, 146, 116],
      [3, 58, 36, 2, 59, 37],
      [4, 36, 16, 4, 37, 17],
      [4, 36, 12, 4, 37, 13],

      // 10
      [2, 86, 68, 2, 87, 69],
      [4, 69, 43, 1, 70, 44],
      [6, 43, 19, 2, 44, 20],
      [6, 43, 15, 2, 44, 16],

      // 11
      [4, 101, 81],
      [1, 80, 50, 4, 81, 51],
      [4, 50, 22, 4, 51, 23],
      [3, 36, 12, 8, 37, 13],

      // 12
      [2, 116, 92, 2, 117, 93],
      [6, 58, 36, 2, 59, 37],
      [4, 46, 20, 6, 47, 21],
      [7, 42, 14, 4, 43, 15],

      // 13
      [4, 133, 107],
      [8, 59, 37, 1, 60, 38],
      [8, 44, 20, 4, 45, 21],
      [12, 33, 11, 4, 34, 12],

      // 14
      [3, 145, 115, 1, 146, 116],
      [4, 64, 40, 5, 65, 41],
      [11, 36, 16, 5, 37, 17],
      [11, 36, 12, 5, 37, 13],

      // 15
      [5, 109, 87, 1, 110, 88],
      [5, 65, 41, 5, 66, 42],
      [5, 54, 24, 7, 55, 25],
      [11, 36, 12, 7, 37, 13],

      // 16
      [5, 122, 98, 1, 123, 99],
      [7, 73, 45, 3, 74, 46],
      [15, 43, 19, 2, 44, 20],
      [3, 45, 15, 13, 46, 16],

      // 17
      [1, 135, 107, 5, 136, 108],
      [10, 74, 46, 1, 75, 47],
      [1, 50, 22, 15, 51, 23],
      [2, 42, 14, 17, 43, 15],

      // 18
      [5, 150, 120, 1, 151, 121],
      [9, 69, 43, 4, 70, 44],
      [17, 50, 22, 1, 51, 23],
      [2, 42, 14, 19, 43, 15],

      // 19
      [3, 141, 113, 4, 142, 114],
      [3, 70, 44, 11, 71, 45],
      [17, 47, 21, 4, 48, 22],
      [9, 39, 13, 16, 40, 14],

      // 20
      [3, 135, 107, 5, 136, 108],
      [3, 67, 41, 13, 68, 42],
      [15, 54, 24, 5, 55, 25],
      [15, 43, 15, 10, 44, 16],

      // 21
      [4, 144, 116, 4, 145, 117],
      [17, 68, 42],
      [17, 50, 22, 6, 51, 23],
      [19, 46, 16, 6, 47, 17],

      // 22
      [2, 139, 111, 7, 140, 112],
      [17, 74, 46],
      [7, 54, 24, 16, 55, 25],
      [34, 37, 13],

      // 23
      [4, 151, 121, 5, 152, 122],
      [4, 75, 47, 14, 76, 48],
      [11, 54, 24, 14, 55, 25],
      [16, 45, 15, 14, 46, 16],

      // 24
      [6, 147, 117, 4, 148, 118],
      [6, 73, 45, 14, 74, 46],
      [11, 54, 24, 16, 55, 25],
      [30, 46, 16, 2, 47, 17],

      // 25
      [8, 132, 106, 4, 133, 107],
      [8, 75, 47, 13, 76, 48],
      [7, 54, 24, 22, 55, 25],
      [22, 45, 15, 13, 46, 16],

      // 26
      [10, 142, 114, 2, 143, 115],
      [19, 74, 46, 4, 75, 47],
      [28, 50, 22, 6, 51, 23],
      [33, 46, 16, 4, 47, 17],

      // 27
      [8, 152, 122, 4, 153, 123],
      [22, 73, 45, 3, 74, 46],
      [8, 53, 23, 26, 54, 24],
      [12, 45, 15, 28, 46, 16],

      // 28
      [3, 147, 117, 10, 148, 118],
      [3, 73, 45, 23, 74, 46],
      [4, 54, 24, 31, 55, 25],
      [11, 45, 15, 31, 46, 16],

      // 29
      [7, 146, 116, 7, 147, 117],
      [21, 73, 45, 7, 74, 46],
      [1, 53, 23, 37, 54, 24],
      [19, 45, 15, 26, 46, 16],

      // 30
      [5, 145, 115, 10, 146, 116],
      [19, 75, 47, 10, 76, 48],
      [15, 54, 24, 25, 55, 25],
      [23, 45, 15, 25, 46, 16],

      // 31
      [13, 145, 115, 3, 146, 116],
      [2, 74, 46, 29, 75, 47],
      [42, 54, 24, 1, 55, 25],
      [23, 45, 15, 28, 46, 16],

      // 32
      [17, 145, 115],
      [10, 74, 46, 23, 75, 47],
      [10, 54, 24, 35, 55, 25],
      [19, 45, 15, 35, 46, 16],

      // 33
      [17, 145, 115, 1, 146, 116],
      [14, 74, 46, 21, 75, 47],
      [29, 54, 24, 19, 55, 25],
      [11, 45, 15, 46, 46, 16],

      // 34
      [13, 145, 115, 6, 146, 116],
      [14, 74, 46, 23, 75, 47],
      [44, 54, 24, 7, 55, 25],
      [59, 46, 16, 1, 47, 17],

      // 35
      [12, 151, 121, 7, 152, 122],
      [12, 75, 47, 26, 76, 48],
      [39, 54, 24, 14, 55, 25],
      [22, 45, 15, 41, 46, 16],

      // 36
      [6, 151, 121, 14, 152, 122],
      [6, 75, 47, 34, 76, 48],
      [46, 54, 24, 10, 55, 25],
      [2, 45, 15, 64, 46, 16],

      // 37
      [17, 152, 122, 4, 153, 123],
      [29, 74, 46, 14, 75, 47],
      [49, 54, 24, 10, 55, 25],
      [24, 45, 15, 46, 46, 16],

      // 38
      [4, 152, 122, 18, 153, 123],
      [13, 74, 46, 32, 75, 47],
      [48, 54, 24, 14, 55, 25],
      [42, 45, 15, 32, 46, 16],

      // 39
      [20, 147, 117, 4, 148, 118],
      [40, 75, 47, 7, 76, 48],
      [43, 54, 24, 22, 55, 25],
      [10, 45, 15, 67, 46, 16],

      // 40
      [19, 148, 118, 6, 149, 119],
      [18, 75, 47, 31, 76, 48],
      [34, 54, 24, 34, 55, 25],
      [20, 45, 15, 61, 46, 16]
    ];

    var qrRSBlock = function(totalCount, dataCount) {
      var _this = {};
      _this.totalCount = totalCount;
      _this.dataCount = dataCount;
      return _this;
    };

    var _this = {};

    var getRsBlockTable = function(typeNumber, errorCorrectionLevel) {

      switch(errorCorrectionLevel) {
      case QRErrorCorrectionLevel.L :
        return RS_BLOCK_TABLE[(typeNumber - 1) * 4 + 0];
      case QRErrorCorrectionLevel.M :
        return RS_BLOCK_TABLE[(typeNumber - 1) * 4 + 1];
      case QRErrorCorrectionLevel.Q :
        return RS_BLOCK_TABLE[(typeNumber - 1) * 4 + 2];
      case QRErrorCorrectionLevel.H :
        return RS_BLOCK_TABLE[(typeNumber - 1) * 4 + 3];
      default :
        return undefined;
      }
    };

    _this.getRSBlocks = function(typeNumber, errorCorrectionLevel) {

      var rsBlock = getRsBlockTable(typeNumber, errorCorrectionLevel);

      if (typeof rsBlock == 'undefined') {
        throw 'bad rs block @ typeNumber:' + typeNumber +
            '/errorCorrectionLevel:' + errorCorrectionLevel;
      }

      var length = rsBlock.length / 3;

      var list = [];

      for (var i = 0; i < length; i += 1) {

        var count = rsBlock[i * 3 + 0];
        var totalCount = rsBlock[i * 3 + 1];
        var dataCount = rsBlock[i * 3 + 2];

        for (var j = 0; j < count; j += 1) {
          list.push(qrRSBlock(totalCount, dataCount) );
        }
      }

      return list;
    };

    return _this;
  }();

  //---------------------------------------------------------------------
  // qrBitBuffer
  //---------------------------------------------------------------------

  var qrBitBuffer = function() {

    var _buffer = [];
    var _length = 0;

    var _this = {};

    _this.getBuffer = function() {
      return _buffer;
    };

    _this.getAt = function(index) {
      var bufIndex = Math.floor(index / 8);
      return ( (_buffer[bufIndex] >>> (7 - index % 8) ) & 1) == 1;
    };

    _this.put = function(num, length) {
      for (var i = 0; i < length; i += 1) {
        _this.putBit( ( (num >>> (length - i - 1) ) & 1) == 1);
      }
    };

    _this.getLengthInBits = function() {
      return _length;
    };

    _this.putBit = function(bit) {

      var bufIndex = Math.floor(_length / 8);
      if (_buffer.length <= bufIndex) {
        _buffer.push(0);
      }

      if (bit) {
        _buffer[bufIndex] |= (0x80 >>> (_length % 8) );
      }

      _length += 1;
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // qrNumber
  //---------------------------------------------------------------------

  var qrNumber = function(data) {

    var _mode = QRMode.MODE_NUMBER;
    var _data = data;

    var _this = {};

    _this.getMode = function() {
      return _mode;
    };

    _this.getLength = function(buffer) {
      return _data.length;
    };

    _this.write = function(buffer) {

      var data = _data;

      var i = 0;

      while (i + 2 < data.length) {
        buffer.put(strToNum(data.substring(i, i + 3) ), 10);
        i += 3;
      }

      if (i < data.length) {
        if (data.length - i == 1) {
          buffer.put(strToNum(data.substring(i, i + 1) ), 4);
        } else if (data.length - i == 2) {
          buffer.put(strToNum(data.substring(i, i + 2) ), 7);
        }
      }
    };

    var strToNum = function(s) {
      var num = 0;
      for (var i = 0; i < s.length; i += 1) {
        num = num * 10 + chatToNum(s.charAt(i) );
      }
      return num;
    };

    var chatToNum = function(c) {
      if ('0' <= c && c <= '9') {
        return c.charCodeAt(0) - '0'.charCodeAt(0);
      }
      throw 'illegal char :' + c;
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // qrAlphaNum
  //---------------------------------------------------------------------

  var qrAlphaNum = function(data) {

    var _mode = QRMode.MODE_ALPHA_NUM;
    var _data = data;

    var _this = {};

    _this.getMode = function() {
      return _mode;
    };

    _this.getLength = function(buffer) {
      return _data.length;
    };

    _this.write = function(buffer) {

      var s = _data;

      var i = 0;

      while (i + 1 < s.length) {
        buffer.put(
          getCode(s.charAt(i) ) * 45 +
          getCode(s.charAt(i + 1) ), 11);
        i += 2;
      }

      if (i < s.length) {
        buffer.put(getCode(s.charAt(i) ), 6);
      }
    };

    var getCode = function(c) {

      if ('0' <= c && c <= '9') {
        return c.charCodeAt(0) - '0'.charCodeAt(0);
      } else if ('A' <= c && c <= 'Z') {
        return c.charCodeAt(0) - 'A'.charCodeAt(0) + 10;
      } else {
        switch (c) {
        case ' ' : return 36;
        case '$' : return 37;
        case '%' : return 38;
        case '*' : return 39;
        case '+' : return 40;
        case '-' : return 41;
        case '.' : return 42;
        case '/' : return 43;
        case ':' : return 44;
        default :
          throw 'illegal char :' + c;
        }
      }
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // qr8BitByte
  //---------------------------------------------------------------------

  var qr8BitByte = function(data) {

    var _mode = QRMode.MODE_8BIT_BYTE;
    var _data = data;
    var _bytes = qrcode.stringToBytes(data);

    var _this = {};

    _this.getMode = function() {
      return _mode;
    };

    _this.getLength = function(buffer) {
      return _bytes.length;
    };

    _this.write = function(buffer) {
      for (var i = 0; i < _bytes.length; i += 1) {
        buffer.put(_bytes[i], 8);
      }
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // qrKanji
  //---------------------------------------------------------------------

  var qrKanji = function(data) {

    var _mode = QRMode.MODE_KANJI;
    var _data = data;

    var stringToBytes = qrcode.stringToBytesFuncs['SJIS'];
    if (!stringToBytes) {
      throw 'sjis not supported.';
    }
    !function(c, code) {
      // self test for sjis support.
      var test = stringToBytes(c);
      if (test.length != 2 || ( (test[0] << 8) | test[1]) != code) {
        throw 'sjis not supported.';
      }
    }('\u53cb', 0x9746);

    var _bytes = stringToBytes(data);

    var _this = {};

    _this.getMode = function() {
      return _mode;
    };

    _this.getLength = function(buffer) {
      return ~~(_bytes.length / 2);
    };

    _this.write = function(buffer) {

      var data = _bytes;

      var i = 0;

      while (i + 1 < data.length) {

        var c = ( (0xff & data[i]) << 8) | (0xff & data[i + 1]);

        if (0x8140 <= c && c <= 0x9FFC) {
          c -= 0x8140;
        } else if (0xE040 <= c && c <= 0xEBBF) {
          c -= 0xC140;
        } else {
          throw 'illegal char at ' + (i + 1) + '/' + c;
        }

        c = ( (c >>> 8) & 0xff) * 0xC0 + (c & 0xff);

        buffer.put(c, 13);

        i += 2;
      }

      if (i < data.length) {
        throw 'illegal char at ' + (i + 1);
      }
    };

    return _this;
  };

  //=====================================================================
  // GIF Support etc.
  //

  //---------------------------------------------------------------------
  // byteArrayOutputStream
  //---------------------------------------------------------------------

  var byteArrayOutputStream = function() {

    var _bytes = [];

    var _this = {};

    _this.writeByte = function(b) {
      _bytes.push(b & 0xff);
    };

    _this.writeShort = function(i) {
      _this.writeByte(i);
      _this.writeByte(i >>> 8);
    };

    _this.writeBytes = function(b, off, len) {
      off = off || 0;
      len = len || b.length;
      for (var i = 0; i < len; i += 1) {
        _this.writeByte(b[i + off]);
      }
    };

    _this.writeString = function(s) {
      for (var i = 0; i < s.length; i += 1) {
        _this.writeByte(s.charCodeAt(i) );
      }
    };

    _this.toByteArray = function() {
      return _bytes;
    };

    _this.toString = function() {
      var s = '';
      s += '[';
      for (var i = 0; i < _bytes.length; i += 1) {
        if (i > 0) {
          s += ',';
        }
        s += _bytes[i];
      }
      s += ']';
      return s;
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // base64EncodeOutputStream
  //---------------------------------------------------------------------

  var base64EncodeOutputStream = function() {

    var _buffer = 0;
    var _buflen = 0;
    var _length = 0;
    var _base64 = '';

    var _this = {};

    var writeEncoded = function(b) {
      _base64 += String.fromCharCode(encode(b & 0x3f) );
    };

    var encode = function(n) {
      if (n < 0) {
        // error.
      } else if (n < 26) {
        return 0x41 + n;
      } else if (n < 52) {
        return 0x61 + (n - 26);
      } else if (n < 62) {
        return 0x30 + (n - 52);
      } else if (n == 62) {
        return 0x2b;
      } else if (n == 63) {
        return 0x2f;
      }
      throw 'n:' + n;
    };

    _this.writeByte = function(n) {

      _buffer = (_buffer << 8) | (n & 0xff);
      _buflen += 8;
      _length += 1;

      while (_buflen >= 6) {
        writeEncoded(_buffer >>> (_buflen - 6) );
        _buflen -= 6;
      }
    };

    _this.flush = function() {

      if (_buflen > 0) {
        writeEncoded(_buffer << (6 - _buflen) );
        _buffer = 0;
        _buflen = 0;
      }

      if (_length % 3 != 0) {
        // padding
        var padlen = 3 - _length % 3;
        for (var i = 0; i < padlen; i += 1) {
          _base64 += '=';
        }
      }
    };

    _this.toString = function() {
      return _base64;
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // base64DecodeInputStream
  //---------------------------------------------------------------------

  var base64DecodeInputStream = function(str) {

    var _str = str;
    var _pos = 0;
    var _buffer = 0;
    var _buflen = 0;

    var _this = {};

    _this.read = function() {

      while (_buflen < 8) {

        if (_pos >= _str.length) {
          if (_buflen == 0) {
            return -1;
          }
          throw 'unexpected end of file./' + _buflen;
        }

        var c = _str.charAt(_pos);
        _pos += 1;

        if (c == '=') {
          _buflen = 0;
          return -1;
        } else if (c.match(/^\s$/) ) {
          // ignore if whitespace.
          continue;
        }

        _buffer = (_buffer << 6) | decode(c.charCodeAt(0) );
        _buflen += 6;
      }

      var n = (_buffer >>> (_buflen - 8) ) & 0xff;
      _buflen -= 8;
      return n;
    };

    var decode = function(c) {
      if (0x41 <= c && c <= 0x5a) {
        return c - 0x41;
      } else if (0x61 <= c && c <= 0x7a) {
        return c - 0x61 + 26;
      } else if (0x30 <= c && c <= 0x39) {
        return c - 0x30 + 52;
      } else if (c == 0x2b) {
        return 62;
      } else if (c == 0x2f) {
        return 63;
      } else {
        throw 'c:' + c;
      }
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // gifImage (B/W)
  //---------------------------------------------------------------------

  var gifImage = function(width, height) {

    var _width = width;
    var _height = height;
    var _data = new Array(width * height);

    var _this = {};

    _this.setPixel = function(x, y, pixel) {
      _data[y * _width + x] = pixel;
    };

    _this.write = function(out) {

      //---------------------------------
      // GIF Signature

      out.writeString('GIF87a');

      //---------------------------------
      // Screen Descriptor

      out.writeShort(_width);
      out.writeShort(_height);

      out.writeByte(0x80); // 2bit
      out.writeByte(0);
      out.writeByte(0);

      //---------------------------------
      // Global Color Map

      // black
      out.writeByte(0x00);
      out.writeByte(0x00);
      out.writeByte(0x00);

      // white
      out.writeByte(0xff);
      out.writeByte(0xff);
      out.writeByte(0xff);

      //---------------------------------
      // Image Descriptor

      out.writeString(',');
      out.writeShort(0);
      out.writeShort(0);
      out.writeShort(_width);
      out.writeShort(_height);
      out.writeByte(0);

      //---------------------------------
      // Local Color Map

      //---------------------------------
      // Raster Data

      var lzwMinCodeSize = 2;
      var raster = getLZWRaster(lzwMinCodeSize);

      out.writeByte(lzwMinCodeSize);

      var offset = 0;

      while (raster.length - offset > 255) {
        out.writeByte(255);
        out.writeBytes(raster, offset, 255);
        offset += 255;
      }

      out.writeByte(raster.length - offset);
      out.writeBytes(raster, offset, raster.length - offset);
      out.writeByte(0x00);

      //---------------------------------
      // GIF Terminator
      out.writeString(';');
    };

    var bitOutputStream = function(out) {

      var _out = out;
      var _bitLength = 0;
      var _bitBuffer = 0;

      var _this = {};

      _this.write = function(data, length) {

        if ( (data >>> length) != 0) {
          throw 'length over';
        }

        while (_bitLength + length >= 8) {
          _out.writeByte(0xff & ( (data << _bitLength) | _bitBuffer) );
          length -= (8 - _bitLength);
          data >>>= (8 - _bitLength);
          _bitBuffer = 0;
          _bitLength = 0;
        }

        _bitBuffer = (data << _bitLength) | _bitBuffer;
        _bitLength = _bitLength + length;
      };

      _this.flush = function() {
        if (_bitLength > 0) {
          _out.writeByte(_bitBuffer);
        }
      };

      return _this;
    };

    var getLZWRaster = function(lzwMinCodeSize) {

      var clearCode = 1 << lzwMinCodeSize;
      var endCode = (1 << lzwMinCodeSize) + 1;
      var bitLength = lzwMinCodeSize + 1;

      // Setup LZWTable
      var table = lzwTable();

      for (var i = 0; i < clearCode; i += 1) {
        table.add(String.fromCharCode(i) );
      }
      table.add(String.fromCharCode(clearCode) );
      table.add(String.fromCharCode(endCode) );

      var byteOut = byteArrayOutputStream();
      var bitOut = bitOutputStream(byteOut);

      // clear code
      bitOut.write(clearCode, bitLength);

      var dataIndex = 0;

      var s = String.fromCharCode(_data[dataIndex]);
      dataIndex += 1;

      while (dataIndex < _data.length) {

        var c = String.fromCharCode(_data[dataIndex]);
        dataIndex += 1;

        if (table.contains(s + c) ) {

          s = s + c;

        } else {

          bitOut.write(table.indexOf(s), bitLength);

          if (table.size() < 0xfff) {

            if (table.size() == (1 << bitLength) ) {
              bitLength += 1;
            }

            table.add(s + c);
          }

          s = c;
        }
      }

      bitOut.write(table.indexOf(s), bitLength);

      // end code
      bitOut.write(endCode, bitLength);

      bitOut.flush();

      return byteOut.toByteArray();
    };

    var lzwTable = function() {

      var _map = {};
      var _size = 0;

      var _this = {};

      _this.add = function(key) {
        if (_this.contains(key) ) {
          throw 'dup key:' + key;
        }
        _map[key] = _size;
        _size += 1;
      };

      _this.size = function() {
        return _size;
      };

      _this.indexOf = function(key) {
        return _map[key];
      };

      _this.contains = function(key) {
        return typeof _map[key] != 'undefined';
      };

      return _this;
    };

    return _this;
  };

  var createDataURL = function(width, height, getPixel) {
    var gif = gifImage(width, height);
    for (var y = 0; y < height; y += 1) {
      for (var x = 0; x < width; x += 1) {
        gif.setPixel(x, y, getPixel(x, y) );
      }
    }

    var b = byteArrayOutputStream();
    gif.write(b);

    var base64 = base64EncodeOutputStream();
    var bytes = b.toByteArray();
    for (var i = 0; i < bytes.length; i += 1) {
      base64.writeByte(bytes[i]);
    }
    base64.flush();

    return 'data:image/gif;base64,' + base64;
  };

  //---------------------------------------------------------------------
  // returns qrcode function.

  return qrcode;
}();

// multibyte support
!function() {

  qrcode.stringToBytesFuncs['UTF-8'] = function(s) {
    // http://stackoverflow.com/questions/18729405/how-to-convert-utf8-string-to-byte-array
    function toUTF8Array(str) {
      var utf8 = [];
      for (var i=0; i < str.length; i++) {
        var charcode = str.charCodeAt(i);
        if (charcode < 0x80) utf8.push(charcode);
        else if (charcode < 0x800) {
          utf8.push(0xc0 | (charcode >> 6),
              0x80 | (charcode & 0x3f));
        }
        else if (charcode < 0xd800 || charcode >= 0xe000) {
          utf8.push(0xe0 | (charcode >> 12),
              0x80 | ((charcode>>6) & 0x3f),
              0x80 | (charcode & 0x3f));
        }
        // surrogate pair
        else {
          i++;
          // UTF-16 encodes 0x10000-0x10FFFF by
          // subtracting 0x10000 and splitting the
          // 20 bits of 0x0-0xFFFFF into two halves
          charcode = 0x10000 + (((charcode & 0x3ff)<<10)
            | (str.charCodeAt(i) & 0x3ff));
          utf8.push(0xf0 | (charcode >>18),
              0x80 | ((charcode>>12) & 0x3f),
              0x80 | ((charcode>>6) & 0x3f),
              0x80 | (charcode & 0x3f));
        }
      }
      return utf8;
    }
    return toUTF8Array(s);
  };

}();

(function (factory) {
  if (typeof define === 'function' && define.amd) {
      define([], factory);
  } else if (typeof exports === 'object') {
      module.exports = factory();
  }
}(function () {
    return qrcode;
}));

  return module.exports
})()

/* ─── 配置（持久化在插件自己的 storage 里）─────────────────────────────── */
const STORAGE_KEY = 'phoneRemote.cfg'
const DEFAULTS = {
  ip: '' /* 留空 = 自动探测局域网 IP；也可手填，如 192.168.1.10 */,
  port: '9119',
  user: '',
  pass: '',
  scriptDir: ''
}

const $cfg = atom({ ...DEFAULTS })
let store = null

function saveCfg(next) {
  $cfg.set(next)
  try {
    if (store) store.set(STORAGE_KEY, next)
  } catch {
    /* 持久化失败不影响本次会话使用 */
  }
}

/* ─── ctx.os 的防御式包装 ────────────────────────────────────────────────
   不同版本 API 名可能微调，这里做兜底，避免某个方法缺失就让整页失灵。 */
function osBridge(ctx) {
  const os = (ctx && ctx.os) || {}
  return {
    async copy(text) {
      try {
        if (os.writeClipboard) return Boolean(await os.writeClipboard(text))
      } catch {
        /* 落到下面的 false */
      }
      return false
    },
    notify(message, kind) {
      const payload = { kind: kind || 'info', message }
      // 宿主版本不同签名也不同：对象形式优先（已在官方 wallpaper 插件里确认），
      // 再退回 (message, kind)，最后放弃 —— 通知失败不该影响主流程。
      try {
        if (host && host.notify) {
          host.notify(payload)
          return
        }
      } catch {
        /* 试下一种 */
      }
      try {
        if (os.notify) os.notify(message, kind || 'info')
      } catch {
        /* 通知失败无所谓 */
      }
    },
    open(url) {
      try {
        if (os.openExternal) return Boolean(os.openExternal(url))
      } catch {
        /* 落到下面的 false */
      }
      return false
    },
    reveal(path) {
      try {
        if (os.revealPath) return Boolean(os.revealPath(path))
      } catch {
        /* 落到下面的 false */
      }
      return false
    }
  }
}

function go(path) {
  try {
    const nav = host && (host.navigate || host.open || host.go)
    if (typeof nav === 'function') return nav(path)
  } catch {
    /* 忽略，下面用提示兜底 */
  }
  return false
}

/* ─── 局域网 IP 自动探测 ─────────────────────────────────────────────────
   插件沙箱不给网络枚举 API，但 WebRTC 的 ICE 候选里带着本机内网地址；
   不依赖任何外部服务。拿不到就返回 null（用户仍可手填）。 */
/* 候选打分：真局域网网卡 > 虚拟网卡。
   192.168.x 最像家用/办公网（VirtualBox 占着 56/57 段，压低）；
   10.x 常见于办公网；172.16-31 是 Docker/Hyper-V/WSL 虚拟网卡的高发段。 */
function ipScore(ip) {
  if (!ip) return 0
  if (ip.indexOf('127.') === 0 || ip.indexOf('169.254.') === 0) return 0
  if (/^192\.168\./.test(ip)) return /^192\.168\.(56|57)\./.test(ip) ? 1 : 3
  if (/^10\./.test(ip)) return 2
  if (/^172\.(1[6-9]|2\d|3[01])\./.test(ip)) return 1
  return 1
}

function detectLanIp() {
  return new Promise(resolve => {
    let done = false
    let best = null
    const finish = value => {
      if (done) return
      done = true
      resolve(value)
    }
    // 超时兜底：交出目前最优的候选（可能仍是 null，用户还能手填）
    const timer = setTimeout(() => finish(best), 2500)
    try {
      const pc = new RTCPeerConnection({ iceServers: [] })
      pc.createDataChannel('probe')
      // ICE 候选会把所有网卡都报一遍，Hyper-V / WSL / VMware 的虚拟网卡（典型 172.26.x）
      // 经常排在真实网卡前面 —— 所以不能拿到第一个就用，要收完再挑分最高的。
      pc.onicecandidate = e => {
        const cand = e && e.candidate && e.candidate.candidate
        if (!cand) {
          // 候选收集结束：交出当前最优解
          clearTimeout(timer)
          try {
            pc.close()
          } catch {
            /* 无所谓 */
          }
          return finish(best)
        }
        const m = /([0-9]{1,3}([.][0-9]{1,3}){3})/.exec(cand)
        if (m && ipScore(m[1]) > ipScore(best)) best = m[1]
      }
      pc.createOffer()
        .then(o => pc.setLocalDescription(o))
        .catch(() => {
          clearTimeout(timer)
          finish(null)
        })
    } catch {
      clearTimeout(timer)
      finish(null)
    }
  })
}

/* ─── 面板改密码：借 Hermes 给插件的后端通道 ───────────────────────────────
   面板只能画界面，改 config.yaml / 重启服务都得下有后端。官方通道是
   ctx.rest(path) → /api/plugins/phone-remote/<path>（走桌面版自己的 IPC 桥，
   同源、免 CORS、自动带当前 profile），后端实现见仓库 dashboard/plugin_api.py。
   后端没装时 rest 会抛错 —— 这时给一句人话提示，不是白屏。 */
const PW_ALPHABET = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789'
/* 刻意去掉 0 O 1 l i：手机小键盘上分不清，历史踩过「密码没敲错但就是登不上」。 */
function randomPassword(len) {
  const n = Math.max(len || 16, 12)
  const rnd = k => {
    const b = new Uint32Array(k)
    if (typeof crypto !== 'undefined' && crypto.getRandomValues) crypto.getRandomValues(b)
    else for (let i = 0; i < k; i++) b[i] = Math.floor(Math.random() * 4294967296)
    return b
  }
  const buf = rnd(n)
  const out = Array.from({ length: n }, (_, i) => PW_ALPHABET[buf[i] % PW_ALPHABET.length])
  /* 四类各塞一个：策略要求，见 dashboard/plugin_api.py password_problem()。
     PW_ALPHABET 就是「23 小写 + 23 大写 + 8 数字」拼的，切片拿到三类，符号另给。 */
  const sets = [PW_ALPHABET.slice(0, 23), PW_ALPHABET.slice(23, 46), PW_ALPHABET.slice(46), '!@#$%^&*-_=+']
  const pick = rnd(sets.length)
  sets.forEach((s, i) => { out[i] = s[pick[i] % s.length] })
  for (let i = n - 1; i > 0; i--) {           // 不洗牌前 4 位永远是「小写大写数字符号」
    const j = buf[i] % (i + 1)
    const t = out[i]; out[i] = out[j]; out[j] = t
  }
  return out.join('')
}

function restBridge(ctx) {
  const fn = ctx && typeof ctx.rest === 'function' ? ctx.rest.bind(ctx) : null
  return async (path, opts) => {
    if (!fn) throw new Error('当前桌面版没给插件后端通道（ctx.rest 不存在）')
    return await fn(path, opts)
  }
}

/* 后端抛的错统一成一句话：FastAPI 的 detail 优先，其次 message。 */
function errText(e) {
  const d = (e && (e.detail || e.message)) || e
  return typeof d === 'string' ? d : JSON.stringify(d)
}

/* ─── 服务在线探测 ───────────────────────────────────────────────────────
   no-cors 模式：读不到状态码，但「连得上」就说明 9119 在监听。
   浏览器 CSP 若拦掉请求会走 catch，此时给「未检测到」而不是误报在线。 */
function useServiceStatus(url) {
  const [state, setState] = useState({ phase: 'checking', at: 0 })
  const [nonce, setNonce] = useState(0)
  useEffect(() => {
    let alive = true
    const probe = async () => {
      try {
        await fetch(url, { mode: 'no-cors', cache: 'no-store' })
        if (alive) setState({ phase: 'online', at: Date.now() })
      } catch {
        if (alive) setState({ phase: 'offline', at: Date.now() })
      }
    }
    setState({ phase: 'checking', at: Date.now() })
    probe()
    const id = setInterval(probe, 5000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [url, nonce])
  return [state, () => setNonce(n => n + 1)]
}

/* ─── 样式（一律走主题变量，深浅色自动跟随）───────────────────────────── */
const S = {
  root: {
    height: '100%',
    overflow: 'auto',
    padding: '20px 24px 28px',
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
    color: 'var(--ui-text-primary)',
    fontSize: '13px',
    lineHeight: 1.6
  },
  title: { fontSize: '16px', fontWeight: 600 },
  sub: { color: 'var(--ui-text-secondary)', fontSize: '12px' },
  card: {
    display: 'flex',
    gap: '20px',
    alignItems: 'flex-start',
    flexWrap: 'wrap',
    padding: '16px',
    borderRadius: '10px',
    background: 'var(--ui-bg-quaternary)',
    border: '1px solid color-mix(in srgb, var(--ui-stroke-secondary) 55%, transparent)'
  },
  col: { flex: '1 1 280px', minWidth: '260px', display: 'flex', flexDirection: 'column', gap: '10px' },
  row: { display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' },
  key: { color: 'var(--ui-text-secondary)', flex: '0 0 auto', width: '44px' },
  val: {
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
    fontSize: '12px',
    flex: '1 1 auto',
    minWidth: '120px',
    wordBreak: 'break-all'
  },
  steps: { margin: 0, paddingLeft: '18px', color: 'var(--ui-text-secondary)', display: 'flex', flexDirection: 'column', gap: '2px' },
  note: {
    display: 'flex',
    gap: '8px',
    padding: '8px 10px',
    borderRadius: '8px',
    background: 'var(--chrome-action-hover)',
    color: 'var(--ui-text-secondary)',
    fontSize: '12px'
  },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '10px', marginTop: '10px' },
  field: { display: 'flex', alignItems: 'center', gap: '8px' },
  fieldKey: { color: 'var(--ui-text-secondary)', width: '70px', flex: '0 0 auto' },
  statusBar: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    flexWrap: 'wrap',
    padding: '7px 10px',
    borderRadius: '8px',
    background: 'var(--chrome-action-hover)',
    fontSize: '12px'
  },
  dot: { width: '8px', height: '8px', borderRadius: '50%', flex: '0 0 auto' },
  card2: {
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    padding: '14px 16px',
    borderRadius: '10px',
    background: 'var(--ui-bg-quaternary)',
    border: '1px solid color-mix(in srgb, var(--ui-stroke-secondary) 55%, transparent)'
  },
  cardTitle: { fontSize: '13px', fontWeight: 600 },
  tabs: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    flexWrap: 'wrap',
    padding: '4px',
    borderRadius: '10px',
    background: 'var(--chrome-action-hover)'
  },
  grid2: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px' },
  okMsg: { fontSize: '12px', color: 'var(--ui-accent)', whiteSpace: 'pre-wrap' },
  warnMsg: { fontSize: '12px', color: 'var(--ui-text-secondary)', whiteSpace: 'pre-wrap' },
}

/* ─── 二维码渲染：把矩阵按行合并成一条 SVG path ───────────────────────── */
function QrImage({ text, size }) {
  const { d, n } = useMemo(() => {
    const qr = makeQr(0, 'M')
    qr.addData(text)
    qr.make()
    const count = qr.getModuleCount()
    const parts = []
    for (let r = 0; r < count; r++) {
      let c = 0
      while (c < count) {
        if (qr.isDark(r, c)) {
          const start = c
          while (c < count && qr.isDark(r, c)) c++
          parts.push('M' + start + ' ' + r + 'h' + (c - start) + 'v1h-' + (c - start) + 'z')
        } else {
          c++
        }
      }
    }
    return { d: parts.join(''), n: count }
  }, [text])

  // 二维码必须白底黑块才能被扫（暗色模式下也不能反色），所以这里固定用白/黑，
  // 是功能性例外，不跟随主题配色。
  return jsx('div', {
    style: {
      background: '#ffffff',
      padding: '12px',
      borderRadius: '10px',
      lineHeight: 0,
      flex: '0 0 auto'
    },
    children: jsx('svg', {
      width: size,
      height: size,
      viewBox: '0 0 ' + n + ' ' + n,
      shapeRendering: 'crispEdges',
      children: jsx('path', { d, fill: '#000000' })
    })
  })
}

/* ─── 一行「标签 + 值 + 复制」────────────────────────────────────────── */
function Field({ label, value, secret, revealed, onToggle, onCopy }) {
  return jsxs('div', {
    style: S.row,
    children: [
      jsx('span', { style: S.key, children: label }),
      jsx('span', {
        style: S.val,
        children: secret && !revealed ? '••••••••' : value || '（未设置）'
      }),
      secret
        ? jsx(Button, {
            variant: 'text',
            size: 'inline',
            onClick: onToggle,
            children: revealed ? '隐藏' : '显示'
          })
        : null,
      jsx(Button, { variant: 'text', size: 'inline', onClick: onCopy, children: '复制' })
    ]
  })
}

/* ─── 页面主体 ───────────────────────────────────────────────────────── */
function PhonePage({ ctx }) {
  const cfg = useValue($cfg)
  const os = osBridge(ctx)
  const [revealed, setRevealed] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [draft, setDraft] = useState(null)
  const [ipHint, setIpHint] = useState(null)
  const rest = useMemo(() => restBridge(ctx), [ctx])
  const [pw, setPw] = useState('')
  const [pwShow, setPwShow] = useState(false)
  const [pwBusy, setPwBusy] = useState('')
  const [pwMsg, setPwMsg] = useState(null)
  const [svc, setSvc] = useState({ phase: 'loading' })
  const [log, setLog] = useState(null)
  const [mode, setMode] = useState('lan')                 // lan = 同一 WiFi；net = 公网隧道
  const [tun, setTun] = useState({ phase: 'loading' })    // 公网隧道状态
  const [tunArm, setTunArm] = useState(false)              // 「开启公网链接」的两段式批准
  const [pair, setPair] = useState({ phase: 'loading', busy: false })   // 扫码配对：每次新 token，用一次作废

  const doPair = async action => {
    setPair(p => ({ ...p, busy: true }))
    try {
      const res = await rest('/pair', { method: 'POST', body: { action } })
      setPair({ phase: 'ready', busy: false, ...(res || {}) })
      os.notify(
        action === 'new'
          ? '配对链接已生成：10 分钟内有效，用一次就作废'
          : action === 'approve'
            ? '已批准这台手机，它正在进入'
            : '已拒绝这台手机',
        action === 'deny' ? 'warn' : 'info'
      )
    } catch (e) {
      os.notify('配对操作失败：' + String((e && e.message) || e), 'warn')
      setPair(p => ({ ...p, busy: false }))
    }
  }

  // 手机那头等着的时候，每 2.5 秒看一眼：扫开没、批没批、过期没
  useEffect(() => {
    if (mode !== 'net') return undefined
    let stop = false
    const tick = async () => {
      try {
        const r = await rest('/pair')
        if (!stop) setPair(prev => ({ ...prev, ...(r || {}), phase: 'ready', busy: prev.busy }))
      } catch (e) {
        if (!stop) setPair(prev => ({ ...prev, phase: 'error', error: String((e && e.message) || e) }))
      }
    }
    tick()
    const id = setInterval(tick, 2500)
    return () => {
      stop = true
      clearInterval(id)
    }
  }, [mode])

  const [ttlMin, setTtlMin] = useState(120)                // 开多久（分钟）


  const link = 'http://' + cfg.ip + ':' + cfg.port + '/'
  const localLink = 'http://127.0.0.1:' + cfg.port + '/'
  const d = draft || cfg

  const [status, recheck] = useServiceStatus('http://127.0.0.1:' + cfg.port + '/api/status')

  // 只在挂载时探测一次本机内网 IP；探测失败就什么都不显示，用户仍能手填。
  useEffect(() => {
    let alive = true
    detectLanIp().then(ip => {
      if (alive && ip && ip !== $cfg.get().ip) setIpHint(ip)
    })
    return () => {
      alive = false
    }
  }, [])

  const loadLog = () => rest('/login-log').then(d => setLog(d)).catch(() => {})

  // 公网隧道状态：后端自己起过就还在，面板重开也能认回来。
  const loadTun = () =>
    rest('/tunnel')
      .then(d => setTun({ phase: 'ok', data: d }))
      .catch(e => setTun({ phase: 'error', error: errText(e) }))

  // 挂载时问一次后端：账号 / 有没有设过密码 / 面板在不在跑。
  useEffect(() => {
    let alive = true
    rest('/status')
      .then(d => {
        if (alive) setSvc({ phase: 'ok', data: d })
      })
      .catch(e => {
        if (alive) setSvc({ phase: 'error', error: String((e && e.message) || e) })
      })
    loadLog()
    loadTun()
    return () => {
      alive = false
    }
  }, [rest])

  const edit = patch => setDraft({ ...d, ...patch })

  const sayPw = (text, ok) => setPwMsg({ text, ok })

  const doRandom = () => {
    const p = randomPassword(16)
    setPw(p)
    setPwShow(true)
    sayPw('已生成随机密码（去掉了容易看错的字符），点「确认更改」写入', true)
  }

  const doChange = async () => {
    if (pwBusy) return
    const value = pw.trim()
    if (!value) {
      sayPw('先填新密码，或点「随机密码」生成一个', false)
      return
    }
    setPwBusy('save')
    try {
      const res = await rest('/password', { method: 'POST', body: { password: value, username: cfg.user || undefined } })
      const user = (res && res.username) || cfg.user
      saveCfg({ ...cfg, user, pass: value }) // 面板上显示的密码跟着换新（明文只落在插件自己的 storage）
      setPw('')
      sayPw('已写入 config.yaml · 账号 ' + user + ' 的新密码要等「重启面板」之后才生效', true)
      os.notify('密码已更新，点「重启面板」生效', 'info')
    } catch (e) {
      sayPw('改密码失败：' + ((e && e.message) || e), false)
    } finally {
      setPwBusy('')
    }
  }

  const doRestart = async () => {
    if (pwBusy) return
    setPwBusy('restart')
    try {
      const res = await rest('/restart', { method: 'POST', body: { port: Number(cfg.port) || 9119 } })
      if (res && res.ok) {
        sayPw('面板已重启 · ' + (res.lan_url || '端口 ' + res.port) + '（清掉 ' + (res.killed || []).length + ' 个旧进程）', true)
        recheck()
        loadLog()
        os.notify('面板已重启', 'info')
      } else {
        sayPw('面板没起来：' + ((res && res.detail) || '未知原因') + ((res && res.tail) ? '\n' + res.tail : ''), false)
      }
    } catch (e) {
      sayPw('重启失败：' + ((e && e.message) || e), false)
    } finally {
      setPwBusy('')
    }
  }

  const svcUp = !!(svc.data && svc.data.running) || status.phase === 'online'
  const tunUrl = (tun.data && tun.data.url) || ''
  const tunBusy = tun.phase === 'busy'
  const ttlOf = m => (m % 60 === 0 ? m / 60 + ' 小时' : m + ' 分钟')

  const doTunnel = async action => {
    if (tunBusy) return
    setTun({ ...tun, phase: 'busy', action })
    try {
      const res = await rest('/tunnel', { method: 'POST', body: { action, port: Number(cfg.port) || 9119, ttl_minutes: Number(ttlMin) || 0 } })
      setTun({ phase: 'ok', data: res })
      if (action === 'stop') {
        os.notify('公网链接已关闭', 'info')
      } else if (action === 'extend') {
        os.notify('已延长 2 小时', 'info')
      } else {
        os.notify('公网链接已开启：' + ((res && res.url) || ''), 'info')
      }
    } catch (e) {
      setTun({ phase: 'error', error: errText(e) })
      os.notify('公网链接操作失败', 'warn')
    }
  }

  const copyTun = async () => {
    if (!tunUrl) return
    const ok = await os.copy(tunUrl)
    os.notify(ok ? '已复制公网地址' : '复制失败，请手动选中地址', ok ? 'info' : 'warn')
  }

  const last = log && log.entries && log.entries.length ? log.entries[log.entries.length - 1] : null
  const logText = !log
    ? ''
    : last
      ? '最近一次手机登录：' + (last.ok ? '成功' : '失败') + (last.ip ? ' · ' + last.ip : '')
      : '还没有手机登录过'

  const svcText =
    svc.phase === 'loading'
      ? '正在读取面板状态…'
      : svc.phase === 'error'
        ? '面板后端还没挂上（重启一次 Hermes 桌面版即可）：' + svc.error
        : '账号 ' +
          svc.data.username +
          ' · ' +
          (svc.data.hash_set ? '已设置密码' : '还没设密码') +
          ' · 服务' +
          (svc.data.running ? '在跑' : '没在跑')

  const statusText =
    status.phase === 'online'
      ? '服务运行中 · ' + localLink
      : status.phase === 'checking'
        ? '正在检测服务…'
        : '未检测到服务（9119 没在跑，或浏览器拦了探测）'

  return jsxs('div', {
    style: S.root,
    children: [
      jsx('div', { style: S.title, children: '连接手机 · 扫码继续对话' }),

      jsxs('div', {
        style: S.statusBar,
        children: [
          jsx('span', {
            style: {
              ...S.dot,
              background:
                status.phase === 'online' ? 'var(--ui-accent)' : 'var(--ui-text-quaternary)'
            }
          }),
          jsx('span', { children: statusText }),
          svcUp
            ? null
            : jsx(Button, {
                variant: 'outline',
                size: 'sm',
                onClick: doRestart,
                children: pwBusy === 'restart' ? '启动中…' : '启动服务'
              }),
          jsx(Button, { variant: 'text', size: 'inline', onClick: recheck, children: '重新检测' })
        ]
      }),

      ipHint
        ? jsxs('div', {
            style: S.note,
            children: [
              jsx('span', {
                style: S.sub,
                children: '探测到本机局域网 IP 是 ' + ipHint + '，当前用的是 ' + (cfg.ip || '自动探测')
              }),
              jsx(Button, {
                variant: 'secondary',
                size: 'inline',
                onClick: () => {
                  saveCfg({ ...cfg, ip: ipHint })
                  setIpHint(null)
                  os.notify('已把局域网 IP 更新为 ' + ipHint, 'info')
                },
                children: '用这个'
              })
            ]
          })
        : null,

      jsxs('div', {
        style: S.tabs,
        children: [
          jsx(Button, {
            variant: mode === 'lan' ? 'secondary' : 'ghost',
            size: 'sm',
            onClick: () => setMode('lan'),
            children: '局域网模式'
          }),
          jsx(Button, {
            variant: mode === 'net' ? 'secondary' : 'ghost',
            size: 'sm',
            onClick: () => setMode('net'),
            children: '互联网模式'
          }),
          jsx('span', {
            style: S.sub,
            children:
              mode === 'lan'
                ? '手机和电脑连同一个 WiFi —— 最快、最稳'
                : '手机用 4G/5G 或别的网也能连 —— 走 Cloudflare 临时公网地址'
          })
        ]
      }),

      mode === 'net'
        ? jsxs('div', {
            style: S.card2,
            children: [
              jsxs('div', {
                style: S.row,
                children: [
                  jsx('span', { style: S.cardTitle, children: '公网链接' }),
                  jsx('span', {
                    style: S.sub,
                    children:
                      tun.phase === 'loading'
                        ? '正在读取…'
                        : tunBusy
                          ? tun.action === 'stop'
                            ? '正在关闭…'
                            : '正在创建（一般 5-15 秒）…'
                          : tunUrl
                            ? '已开启'
                            : '未开启'
                  })
                ]
              }),
              tunUrl
                ? jsxs('div', {
                    style: S.row,
                    children: [
                      jsx('span', { style: S.val, children: tunUrl }),
                      jsx(Button, { variant: 'outline', size: 'sm', onClick: copyTun, children: '复制' }),
                      jsx(Button, {
                        variant: 'outline',
                        size: 'sm',
                        onClick: () => doTunnel('extend'),
                        children: '延长 ' + ttlOf(ttlMin)
                      }),
                      jsx(Button, {
                        variant: 'ghost',
                        size: 'sm',
                        onClick: () => doTunnel('stop'),
                        children: tunBusy ? '处理中…' : '关闭'
                      })
                    ]
                  })
                : jsxs('div', {
                    style: S.row,
                    children: [
                      jsx(Button, {
                        variant: tunArm ? 'default' : 'secondary',
                        size: 'sm',
                        onClick: () => {
                          if (!tunArm) {              // 两段式批准：先点一下，再点才真的开公网（防误触）
                            setTunArm(true)
                            setTimeout(() => setTunArm(false), 8000)   // 走开了就自动撤销，免得下次点一下就把公网开了
                            return
                          }
                          setTunArm(false)
                          doTunnel('start')
                        },
                        children: tunBusy ? '创建中…' : tunArm ? '确认开启（外网可访问）' : '开启公网链接'
                      }),
                      jsx('span', {
                        style: S.sub,
                        children: tunArm
                          ? '确认后 Cloudflare 会分配一个公网地址 —— 谁拿到这个地址都能打开登录页'
                          : '不开的时候，外网完全访问不到这台机器'
                      })
                    ]
                  }),
              tunUrl && tun.expires_at
                ? jsx('span', {
                    style: S.sub,
                    children:
                      '到 ' +
                      new Date(tun.expires_at * 1000).toTimeString().slice(0, 5) +
                      ' 自动关闭 —— 忘了关是这类公网地址最大的风险，所以默认只开 2 小时，要接着用点「延长」。'
                  })
                : null,
              jsx('div', {
                style: S.row,
                children: [
                  jsx('span', { style: S.sub, children: tunUrl ? '延长多久：' : '开多久：' }),
                  jsx('select', {
                    value: String(ttlMin),
                    onChange: e => setTtlMin(Number(e.target.value)),
                    style: {
                      padding: '4px 6px', borderRadius: 6, border: '1px solid currentColor',
                      background: 'transparent', color: 'inherit', fontSize: 12
                    },
                    children: [30, 120, 240, 360, 480, 720, 1440, 2880, 4320].map(m =>
                      jsx('option', { value: String(m), children: ttlOf(m) })
                    )
                  }),
                  jsx('span', { style: S.sub, children: '到点自动断开（最长 72 小时，不给「永不」）' })
                ]
              }),
              jsx('span', {
                style: S.sub,
                children:
                  '地址是临时的：重启了 cloudflared（电脑重启、手动关掉）就会换新的，重开一次扫新码即可；只重启面板不影响它。登录用的还是上面这组账号密码。'
              }),
              tun.phase === 'error' ? jsx('div', { style: S.warnMsg, children: tun.error }) : null,
              tun.phase === 'error'
                ? jsx('span', {
                    style: S.sub,
                    children:
                      '本机需要有 cloudflared.exe（装过 DSH Desktop 就有自带的）；没有的话去 Cloudflare 官网下一个，改名 cloudflared.exe 放进插件目录再点一次。'
                  })
                : null
            ]
          })
        : null,

      mode === 'net'
        ? jsxs('div', {
            style: S.card,
            children: [
              jsxs('div', {
                style: S.row,
                children: [
                  jsx('span', { style: S.cardTitle, children: '扫码配对（手机不用输密码）' }),
                  jsx('span', {
                    style: S.sub,
                    children:
                      pair.phase === 'loading'
                        ? '正在读取…'
                        : pair.phase === 'error'
                          ? '读取失败'
                          : pair.status === 'pending'
                            ? pair.ua
                              ? '手机已打开，等你批准'
                              : '等待手机打开链接…'
                            : pair.status === 'approved'
                              ? '已批准，手机正在进入…'
                              : pair.status === 'expired'
                                ? '上一个链接已过期'
                                : pair.status === 'denied'
                                  ? '已拒绝'
                                  : '没有等着的配对'
                  })
                ]
              }),
              pair.url
                ? jsxs('div', {
                    style: S.row,
                    children: [
                      jsx(QrImage, { text: pair.url, size: 160 }),
                      jsxs('div', {
                        style: S.col,
                        children: [
                          jsx('span', { style: S.val, children: pair.url }),
                          jsx('span', {
                            style: S.sub,
                            children:
                              '用一次就作废' +
                              (pair.expires_at
                                ? '，到 ' +
                                  new Date(pair.expires_at * 1000).toTimeString().slice(0, 5) +
                                  ' 还没批也失效'
                                : '')
                          }),
                          pair.status === 'pending' && (pair.ip || pair.ua)
                            ? jsx('span', {
                                style: S.sub,
                                children:
                                  '来自 ' +
                                  (pair.ip || '手机') +
                                  (pair.ua ? ' · ' + String(pair.ua).slice(0, 44) : '')
                              })
                            : null,
                          jsxs('div', {
                            style: S.row,
                            children: [
                              jsx(Button, {
                                variant: 'default',
                                size: 'sm',
                                disabled: pair.busy || pair.status !== 'pending',
                                onClick: () => doPair('approve'),
                                children: pair.status === 'approved' ? '已批准' : '批准此手机'
                              }),
                              jsx(Button, {
                                variant: 'ghost',
                                size: 'sm',
                                disabled: pair.busy,
                                onClick: () => doPair('deny'),
                                children: '拒绝'
                              }),
                              jsx(Button, {
                                variant: 'outline',
                                size: 'sm',
                                disabled: pair.busy,
                                onClick: () => doPair('new'),
                                children: '换一个新链接'
                              })
                            ]
                          }),
                          jsx('span', {
                            style: S.sub,
                            children:
                              '密码不用给手机：链接泄漏也只是多一个「待批准」的请求，你不点批准就进不来。'
                          })
                        ]
                      })
                    ]
                  })
                : jsxs('div', {
                    style: S.row,
                    children: [
                      jsx(Button, {
                        variant: 'secondary',
                        size: 'sm',
                        disabled: pair.busy || !tunUrl,
                        onClick: () => doPair('new'),
                        children: pair.busy ? '生成中…' : '生成配对链接'
                      }),
                      jsx('span', {
                        style: S.sub,
                        children: tunUrl
                          ? '链接只活 10 分钟，用过 / 过期都得重新生成'
                          : '先点上面的「开启公网链接」，配对链接才有公网地址'
                      })
                    ]
                  }),
              pair.phase === 'error' ? jsx('div', { style: S.warnMsg, children: pair.error }) : null
            ]
          })
        : null,

      jsxs('div', {
        style: S.card,
        children: [
          mode === 'net' && !tunUrl
            ? jsx('span', { style: S.sub, children: '先点上面的「开启公网链接」，这里会变成公网地址的二维码' })
            : jsx(QrImage, { text: mode === 'net' ? tunUrl : link, size: 224 }),
          jsxs('div', {
            style: S.col,
            children: [
              jsxs('ol', {
                style: S.steps,
                children: [
                  jsx('li', {
                    children:
                      mode === 'net'
                        ? '手机（4G/5G 也行）扫左边的码，或直接打开下面的地址'
                        : '手机相机 / 微信「扫一扫」对准左边的二维码'
                  }),
                  jsx('li', { children: '首次打开输入下面这组账号密码，勾选「记住我」' }),
                  jsx('li', { children: '以后手机上就能聊天、切会话、看历史，和电脑端同一套会话' })
                ]
              }),
              jsx(Separator, {}),
              jsx(Field, {
                label: '地址',
                value: mode === 'net' ? tunUrl || '（还没开启公网链接）' : link,
                onCopy: async () => {
                  const target = mode === 'net' ? tunUrl : link
                  if (!target) {
                    os.notify('先在上面点「开启公网链接」', 'warn')
                    return
                  }
                  const ok = await os.copy(target)
                  os.notify(ok ? '已复制手机访问地址' : '复制失败，请手动选中地址', ok ? 'info' : 'warn')
                }
              }),
              jsx(Field, {
                label: '账号',
                value: cfg.user,
                onCopy: async () => {
                  const ok = await os.copy(cfg.user)
                  os.notify(ok ? '已复制账号' : '复制失败', ok ? 'info' : 'warn')
                }
              }),
              jsx(Field, {
                label: '密码',
                value: cfg.pass,
                secret: true,
                revealed,
                onToggle: () => setRevealed(!revealed),
                onCopy: async () => {
                  if (!cfg.pass) {
                    os.notify('还没填密码 —— 点下面「设置」填一次，或在设置里留空后手机端手动输', 'warn')
                    return
                  }
                  const ok = await os.copy(cfg.pass)
                  os.notify(ok ? '已复制密码' : '复制失败', ok ? 'info' : 'warn')
                }
              })
            ]
          })
        ]
      }),

      jsxs('div', {
        style: S.row,
        children: [
          jsx(Button, {
            variant: 'secondary',
            size: 'sm',
            onClick: () => {
              const ok = os.open(localLink)
              if (!ok) os.notify('无法自动打开浏览器，请手动访问 ' + localLink, 'warn')
            },
            children: '打开本机面板'
          }),
          jsx(Button, {
            variant: 'outline',
            size: 'sm',
            onClick: async () => {
              const ok = await os.copy(link)
              os.notify(ok ? '已复制 ' + link : '复制失败，请手动选中地址', ok ? 'info' : 'warn')
            },
            children: '复制手机地址'
          }),
          jsx(Button, {
            variant: 'ghost',
            size: 'sm',
            onClick: () => {
              const ok = os.reveal(cfg.scriptDir)
              if (!ok) os.notify('脚本目录：' + cfg.scriptDir, 'info')
            },
            children: '打开启动脚本文件夹'
          })
        ]
      }),

      jsxs('div', {
        style: S.card2,
        children: [
          jsxs('div', {
            style: S.row,
            children: [
              jsx('span', { style: S.cardTitle, children: '登录密码' }),
              jsx('span', { style: S.sub, children: svcText })
            ]
          }),
          jsxs('div', {
            style: S.grid2,
            children: [
              jsxs('div', {
                style: S.field,
                children: [
                  jsx('span', { style: S.fieldKey, children: '账号' }),
                  jsx(Input, {
                    size: 'sm',
                    value: d.user || '',
                    placeholder: 'admin',
                    onChange: e => edit({ user: e.target.value })
                  })
                ]
              }),
              jsxs('div', {
                style: S.field,
                children: [
                  jsx('span', { style: S.fieldKey, children: '新密码' }),
                  jsx(Input, {
                    size: 'sm',
                    type: pwShow ? 'text' : 'password',
                    value: pw,
                    placeholder: '至少 12 位，含大小写字母+数字+符号',
                    onChange: e => setPw(e.target.value)
                  })
                ]
              })
            ]
          }),
          jsxs('div', {
            style: S.row,
            children: [
              jsx(Button, { variant: 'ghost', size: 'sm', onClick: doRandom, children: '随机密码' }),
              jsx(Button, {
                variant: 'secondary',
                size: 'sm',
                onClick: doChange,
                children: pwBusy === 'save' ? '写入中…' : '确认更改'
              }),
              jsx(Button, {
                variant: 'outline',
                size: 'sm',
                onClick: doRestart,
                children: pwBusy === 'restart' ? (svcUp ? '重启中…' : '启动中…') : svcUp ? '重启面板' : '启动服务'
              }),
              jsx(Button, {
                variant: 'text',
                size: 'inline',
                onClick: () => setPwShow(!pwShow),
                children: pwShow ? '隐藏' : '显示'
              })
            ]
          }),
          logText ? jsx('span', { style: S.sub, children: logText }) : null,
          pwMsg ? jsx('div', { style: pwMsg.ok ? S.okMsg : S.warnMsg, children: pwMsg.text }) : null,
          jsx('span', {
            style: S.sub,
            children: '改完密码要点「重启面板」才生效 —— 密码是服务启动时读进内存的，重启前旧密码照样能登。'
          })
        ]
      }),

      jsxs('div', {
        style: S.note,
        children: [
          jsx('span', { children: '·' }),
          jsxs('span', {
            children: [
              jsx('b', { children: '状态是「未检测到」？' }),
              ' 说明后台服务没在跑 —— 点上面「启动服务」拉起来（等价于双击 ',
              jsx('code', { children: '启动手机网页-Start-Phone-Web.bat' }),
              '，服务监听 0.0.0.0:',
              cfg.port,
              '，防火墙入站规则 ',
              jsx('code', { children: 'Hermes Phone Chat ' + cfg.port }),
              ' 已放行）。'
            ]
          })
        ]
      }),

      jsxs('div', {
        children: [
          jsx(Button, {
            variant: 'text',
            size: 'inline',
            onClick: () => setShowSettings(!showSettings),
            children: (showSettings ? '▾' : '▸') + ' 设置（局域网 IP / 端口 / 显示用的账号密码）'
          }),
          showSettings
            ? jsxs('div', {
                children: [
                  jsxs('div', {
                    style: S.grid,
                    children: [
                      jsxs('div', {
                        style: S.field,
                        children: [
                          jsx('span', { style: S.fieldKey, children: '局域网 IP' }),
                          jsx(Input, {
                            size: 'sm',
                            value: d.ip,
                            placeholder: '192.168.x.x',
                            onChange: e => edit({ ip: e.target.value.trim() })
                          })
                        ]
                      }),
                      jsxs('div', {
                        style: S.field,
                        children: [
                          jsx('span', { style: S.fieldKey, children: '端口' }),
                          jsx(Input, {
                            size: 'sm',
                            value: d.port,
                            placeholder: '9119',
                            onChange: e => edit({ port: e.target.value.trim() })
                          })
                        ]
                      }),
                      jsxs('div', {
                        style: S.field,
                        children: [
                          jsx('span', { style: S.fieldKey, children: '账号' }),
                          jsx(Input, {
                            size: 'sm',
                            value: d.user,
                            placeholder: 'admin',
                            onChange: e => edit({ user: e.target.value })
                          })
                        ]
                      }),
                      jsxs('div', {
                        style: S.field,
                        children: [
                          jsx('span', { style: S.fieldKey, children: '密码' }),
                          jsx(Input, {
                            size: 'sm',
                            type: 'password',
                            value: d.pass,
                            placeholder: 'dashboard 密码',
                            onChange: e => edit({ pass: e.target.value })
                          })
                        ]
                      })
                    ]
                  }),
                  jsxs('div', {
                    style: { ...S.row, marginTop: '10px' },
                    children: [
                      jsx(Button, {
                        variant: 'secondary',
                        size: 'sm',
                        onClick: () => {
                          saveCfg({ ...cfg, ...d, scriptDir: d.scriptDir || DEFAULTS.scriptDir })
                          setDraft(null)
                          os.notify('已保存', 'info')
                        },
                        children: '保存'
                      }),
                      jsx(Button, {
                        variant: 'text',
                        size: 'inline',
                        onClick: () => setDraft({ ...DEFAULTS }),
                        children: '恢复默认'
                      }),
                      jsx('span', {
                        style: S.sub,
                        children: '这里的账号 / 密码只是本机备注（显示用）；真正生效的密码在上面「登录密码」里改。'
                      })
                    ]
                  })
                ]
              })
            : null
        ]
      })
    ]
  })
}

/* ─── 插件注册 ───────────────────────────────────────────────────────── */
export default {
  id: 'phone-remote',
  name: '连接手机',
  register(ctx) {
    // 加载探针：宿主把 renderer console 转发进 logs/desktop.log，
    // 这行日志是「插件确实被加载」的外部可验证证据。
    console.log('[phone-remote] loaded v3 — 连接手机插件已注册（状态灯 + IP 探测 + 面板改密码）')
    try {
      store = ctx.storage
    } catch {
      store = null
    }
    try {
      const saved = store ? store.get(STORAGE_KEY, null) : null
      if (saved && typeof saved === 'object') $cfg.set({ ...DEFAULTS, ...saved })
    } catch {
      /* 读不到就用默认值 */
    }

    const Page = () => jsx(PhonePage, { ctx })

    try {
    ctx.register({
      id: 'phoneRemote.page',
      area: ROUTES_AREA,
      data: { path: '/phone-connect' },
      render: Page
    })

    ctx.register({
      id: 'phoneRemote.nav',
      area: SIDEBAR_NAV_AREA,
      data: { path: '/phone-connect', label: '连接手机', codicon: 'device-mobile' }
    })

    ctx.register({
      id: 'phoneRemote.palette',
      area: PALETTE_AREA,
      data: {
        id: 'phoneRemote.palette',
        label: '连接手机',
        keywords: [
          '手机',
          '扫码',
          '二维码',
          '连接',
          '远程',
          '扫描',
          '配对',
          'phone',
          'qr',
          'mobile',
          'connect',
          'remote',
          'pair'
        ],
        detail: () => 'http://' + $cfg.get().ip + ':' + $cfg.get().port + '/',
        detailVariant: 'muted',
        run: () => {
          if (!go('/phone-connect')) {
            const ok = !!(ctx.os && ctx.os.notify)
            if (ok) ctx.os.notify('请在左侧栏点击「连接手机」', 'info')
          }
        }
      }
    })
    } catch (e) {
      // register 抛异常 = 插件整体加载失败，所以三个入口一起兜住。
      console.error('[phone-remote] register FAIL', e && e.stack ? e.stack : e)
      try {
        if (ctx.os && ctx.os.notify) ctx.os.notify('连接手机插件初始化失败：' + (e && e.message ? e.message : e))
      } catch {
        /* 连提示都发不出就只留日志 */
      }
    }
  }
}
