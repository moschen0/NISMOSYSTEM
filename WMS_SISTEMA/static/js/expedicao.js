/**
 * EXPEDICAO.JS — Lógica client-side do módulo de Expedição
 * Checkin de Entrada, Onda de Picking, Doublecheck e Embala/Fatura.
 */

const Expedicao = (() => {
  function showAlert(elId, message, type) {
    const el = document.getElementById(elId);
    if (!el) return;
    el.className = `alert alert-${type}`;
    el.textContent = message;
    el.style.display = 'block';
  }

  // Very loud warning for doublecheck invalid scans
  function showLoudWarning(message) {
    // Create overlay if not present (template includes it on doublecheck page)
    const overlay = document.getElementById('dc-loud-warning-overlay');
    const boxMsg = document.getElementById('dc-loud-warning-message');
    if (!overlay || !boxMsg) {
      // Fallback to normal alert if overlay missing
      showAlert('doublecheck-alert', message, 'danger');
      return;
    }
    // If overlay already visible, don't retrigger effects (prevents flicker)
    if (overlay.style.display === 'flex') {
      const input = document.getElementById('dc-order-id-input'); if (input) input.focus();
      return;
    }

    boxMsg.textContent = message;
    overlay.style.display = 'flex';

    // play a short beep using WebAudio API (single short tone)
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = 'sine';
      o.frequency.value = 880;
      g.gain.value = 0.08;
      o.connect(g); g.connect(ctx.destination);
      o.start();
      setTimeout(() => { o.stop(); try { ctx.close(); } catch (e) {} }, 120);
    } catch (e) {}

    // Keep the overlay static (no animation) so it doesn't flash.
    const ok = document.getElementById('dc-loud-warning-ok');
    const repeat = document.getElementById('dc-loud-warning-repeat');

    function onKey(e) { if (e.key === 'Escape') { close(); } }
    function close() { overlay.style.display = 'none'; window.removeEventListener('keydown', onKey); }

    ok.onclick = close;
    repeat.onclick = () => { close(); const input = document.getElementById('dc-order-id-input'); if (input) input.focus(); };
    window.addEventListener('keydown', onKey);
  }

  const EXPEDICAO_API_BASE = (window.location && window.location.origin ? window.location.origin : '') + '/expedicao/api';

  async function postJson(url, payload) {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload || {}),
    });
    let data = {};
    try {
      data = await response.json();
    } catch (e) {
      data = {};
    }
    return { ok: response.ok, status: response.status, data };
  }

  // ── CHECKIN DE ENTRADA ──────────────────────────────────────
  const Checkin = {
    init() {
      const input = document.getElementById('master-id-input');
      if (input) {
        input.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            Checkin.scan();
          }
        });
      }
      // Populate horario select on checkin page if empty (fetch from server)
      try {
        const sel = document.getElementById('horario-select-checkin');
        if (sel) {
          // Only fetch if no options besides the placeholder
            if (sel.options.length <= 1) {
            fetch(EXPEDICAO_API_BASE + '/picking/horarios')
              .then(r => r.json())
              .then(j => {
                if (j && Array.isArray(j.horarios)) {
                  j.horarios.forEach(h => {
                    const opt = document.createElement('option');
                    opt.value = h; opt.textContent = h;
                    sel.appendChild(opt);
                  });
                }
              }).catch(()=>{});
          }
        }
      } catch (e) {}
      // Attach refresh button handler and gerar onda button
      try {
        const refreshBtn = document.getElementById('horario-refresh-btn');
        const sel = document.getElementById('horario-select-checkin');
        const gerarBtn = document.getElementById('gerar-onda-btn');
        const alertEl = document.getElementById('picking-alert-checkin');
        function loadHorarios(showEmptyMsg) {
          if (!sel) return;
          fetch(EXPEDICAO_API_BASE + '/picking/horarios')
            .then(r => r.json())
            .then(j => {
              // clear existing non-placeholder options
              for (let i = sel.options.length - 1; i >= 0; i--) {
                if (i === 0) continue;
                sel.remove(i);
              }
              if (j && Array.isArray(j.horarios) && j.horarios.length) {
                j.horarios.forEach(h => {
                  const opt = document.createElement('option'); opt.value = h; opt.textContent = h; sel.appendChild(opt);
                });
                if (alertEl) { alertEl.style.display = 'none'; }
              } else {
                if (showEmptyMsg && alertEl) {
                  alertEl.className = 'alert alert-warning';
                  alertEl.textContent = 'Nenhum horário encontrado.';
                  alertEl.style.display = 'block';
                }
              }
            }).catch(()=>{
              if (showEmptyMsg && alertEl) {
                alertEl.className = 'alert alert-danger';
                alertEl.textContent = 'Erro ao carregar horários.';
                alertEl.style.display = 'block';
              }
            });
        }
        if (refreshBtn) refreshBtn.addEventListener('click', () => loadHorarios(true));
        if (gerarBtn) gerarBtn.addEventListener('click', () => {
          const horario = sel ? sel.value : '';
          if (!horario) {
            if (alertEl) { alertEl.className='alert alert-danger'; alertEl.textContent='Selecione um horário.'; alertEl.style.display='block'; }
            return;
          }
          window.location.href = '/expedicao/picking?horario='+encodeURIComponent(horario);
        });
      } catch (e) {}
    },

    async scan() {
      const masterInput = document.getElementById('master-id-input');
      const clientInput = document.getElementById('client-number-input');
      const orderId = masterInput.value.trim();
      const clientNumber = clientInput ? clientInput.value.trim() : '';

      if (!orderId) {
        showAlert('checkin-alert', 'Informe o ID Master.', 'danger');
        return;
      }

      const { ok, data } = await postJson('/expedicao/api/checkin/scan', {
        order_id: orderId,
        client_number: clientNumber,
      });

      if (!ok) {
        if (data.needs_client_number) {
          document.getElementById('client-number-wrapper').style.display = 'block';
        }
        showAlert('checkin-alert', data.error || 'Erro ao bipar ID Master.', 'danger');
        return;
      }

      masterInput.value = '';
      if (clientInput) clientInput.value = '';
      // If server suggested an endereco for this lote, fill the input.
      try {
        const lote = data.lote;
        if (data.suggested_endereco && lote && lote.id) {
          const container = document.querySelector(`[data-lote-id="${lote.id}"]`);
          if (!container) {
            window.location.reload();
            return;
          }
          const enderecoEl = document.getElementById(`endereco-${lote.id}`);
          if (enderecoEl && !enderecoEl.value) {
            enderecoEl.value = data.suggested_endereco;
          }
          // Append the scanned order to the lote items list if present in DOM
          const ul = container.querySelector('.list-group');
          if (ul) {
            const li = document.createElement('li');
            li.className = 'list-group-item px-0 py-1 font-monospace';
            li.textContent = data.items && data.items.length ? data.items[data.items.length-1].order_id : '';
            ul.appendChild(li);
          }
        } else {
          // No suggestion — do a full reload to reflect server state
          window.location.reload();
        }
      } catch (e) {
        // On error, fallback to reload
        window.location.reload();
      }
    },

    async fechar(loteId) {
      const enderecoInput = document.getElementById(`endereco-${loteId}`);
      const endereco = enderecoInput ? enderecoInput.value.trim() : '';
      if (!endereco) {
        showAlert('checkin-alert', 'Informe o endereçamento para fechar o lote.', 'danger');
        return;
      }
      const { ok, data } = await postJson('/expedicao/api/checkin/fechar', {
        lote_id: loteId,
        endereco,
      });
      if (!ok) {
        showAlert('checkin-alert', data.error || 'Erro ao fechar o lote.', 'danger');
        return;
      }
      window.location.reload();
    },

    async confirmar(loteId) {
      const { ok, data } = await postJson('/expedicao/api/checkin/confirmar', { lote_id: loteId });
      if (!ok) {
        showAlert('checkin-alert', data.error || 'Erro ao confirmar guia.', 'danger');
        return;
      }
      window.location.reload();
    },
  };

  // ── ONDA DE PICKING ─────────────────────────────────────────
  const Picking = {
    async gerarOnda() {
      const select = document.getElementById('horario-select');
      const horario = select.value;
      if (!horario) {
        showAlert('picking-alert', 'Selecione um horário.', 'danger');
        return;
      }
      const { ok, status, data } = await postJson('/expedicao/api/picking/gerar-onda', { horario });
      if (!ok && status === 404) {
        // Compatibilidade com servidores antigos sem endpoint API de gerar onda.
        window.location.href = `/expedicao/picking?horario=${encodeURIComponent(horario)}`;
        return;
      }
      if (!ok) {
        showAlert('picking-alert', data.error || 'Erro ao gerar onda.', 'danger');
        return;
      }
      window.location.href = `/expedicao/picking/onda/${data.onda.id}`;
    },
  };

  // ── PICKING COM DOUBLECHECK ─────────────────────────────────
  const Doublecheck = {
    init() {
      const input = document.getElementById('dc-order-id-input');
      if (input) {
        input.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            Doublecheck.scan();
          }
        });
        input.focus();
      }
      this._syncActionButtons();
      this._updateProgressBar();
    },

    _getProgressState() {
      const confirmedEl = document.getElementById('dc-confirmed');
      const totalEl = document.getElementById('dc-total');
      const confirmed = parseInt(confirmedEl ? confirmedEl.textContent : '0', 10) || 0;
      const total = parseInt(totalEl ? totalEl.textContent : '0', 10) || 0;
      const missing = Math.max(total - confirmed, 0);
      return { confirmed, total, missing };
    },

    _syncActionButtons() {
      const progress = this._getProgressState();
      const finalizarBtn = document.getElementById('dc-finalizar-btn');
      const finalizarFaltaBtn = document.getElementById('dc-finalizar-falta-btn');
      if (finalizarBtn) {
        finalizarBtn.style.display = progress.total > 0 && progress.missing === 0 ? 'block' : 'none';
      }
      if (finalizarFaltaBtn) {
        finalizarFaltaBtn.style.display = progress.total > 0 && progress.missing > 0 ? 'block' : 'none';
      }
    },

    _updateProgressBar() {
      const confirmedEl = document.getElementById('dc-confirmed');
      const totalEl = document.getElementById('dc-total');
      const bar = document.getElementById('dc-progress-bar');
      if (!confirmedEl || !totalEl || !bar) return;
      const confirmed = parseInt(confirmedEl.textContent, 10) || 0;
      const total = parseInt(totalEl.textContent, 10) || 0;
      const pct = total > 0 ? Math.round((confirmed / total) * 100) : 0;
      bar.style.width = `${pct}%`;
      bar.textContent = `${pct}%`;
    },

    async scan() {
      const loteId = document.getElementById('dc-lote-id').value;
      const ondaId = document.getElementById('dc-onda-id').value || null;
      const input = document.getElementById('dc-order-id-input');
      const orderId = input.value.trim();

      if (!orderId) return;

      const { ok, data } = await postJson('/expedicao/api/doublecheck/scan', {
        lote_id: parseInt(loteId, 10),
        onda_id: ondaId ? parseInt(ondaId, 10) : null,
        order_id: orderId,
      });

      input.value = '';
      input.focus();

      if (data.progress) {
        document.getElementById('dc-confirmed').textContent = data.progress.confirmed;
        document.getElementById('dc-total').textContent = data.progress.total;
        this._updateProgressBar();
        this._syncActionButtons();
      }

      if (!ok || data.result === 'nao_pertence') {
        // show a very loud warning overlay on doublecheck page
        const msg = data.message || data.error || 'OS não pertence a este lote ou não existe!';
        showLoudWarning(msg);
        return;
      }

      showAlert('doublecheck-alert', 'ID confirmado.', 'success');
    },

    openLeaderAuthModal() {
      const alertEl = document.getElementById('dc-leader-auth-alert');
      const userInput = document.getElementById('dc-leader-username');
      const passInput = document.getElementById('dc-leader-password');
      if (alertEl) {
        alertEl.style.display = 'none';
        alertEl.textContent = '';
      }
      if (userInput) userInput.value = '';
      if (passInput) passInput.value = '';

      const modalEl = document.getElementById('dcLeaderAuthModal');
      if (modalEl && window.bootstrap && window.bootstrap.Modal) {
        const modal = window.bootstrap.Modal.getOrCreateInstance(modalEl);
        modal.show();
        setTimeout(() => {
          if (userInput) userInput.focus();
        }, 150);
      }
    },

    async finalizarComFalta() {
      const usernameInput = document.getElementById('dc-leader-username');
      const passwordInput = document.getElementById('dc-leader-password');
      const username = usernameInput ? usernameInput.value.trim() : '';
      const password = passwordInput ? passwordInput.value : '';

      if (!username || !password) {
        showAlert('dc-leader-auth-alert', 'Informe login e senha do líder.', 'danger');
        return;
      }

      const modalEl = document.getElementById('dcLeaderAuthModal');
      const { ok, data } = await postJson('/expedicao/api/doublecheck/finalizar', {
        lote_id: parseInt(document.getElementById('dc-lote-id').value, 10),
        leader_username: username,
        leader_password: password,
      });

      if (!ok) {
        showAlert('dc-leader-auth-alert', data.error || 'Autorização do líder inválida.', 'danger');
        return;
      }

      if (modalEl && window.bootstrap && window.bootstrap.Modal) {
        const modal = window.bootstrap.Modal.getOrCreateInstance(modalEl);
        modal.hide();
      }

      if (data.status === 'separado_com_falta') {
        showAlert('doublecheck-alert', `ATENÇÃO: faltam ${data.progress.missing} ID(s) neste lote!`, 'danger');
        window.location.href = '/expedicao/embalagem';
        return;
      }

      showAlert('doublecheck-alert', 'Separação completa! Gerando etiqueta...', 'success');
      if (data.label_url) {
        window.location.href = data.label_url;
      } else {
        window.location.href = '/expedicao/embalagem';
      }
    },

    async finalizar() {
      const loteId = document.getElementById('dc-lote-id').value;
      const { ok, data } = await postJson('/expedicao/api/doublecheck/finalizar', {
        lote_id: parseInt(loteId, 10),
      });
      if (!ok) {
        showAlert('doublecheck-alert', data.error || 'Erro ao finalizar separação.', 'danger');
        return;
      }
      this._syncActionButtons();
      // Notify user about status
      if (data.status === 'separado_com_falta') {
        showAlert('doublecheck-alert', `ATENÇÃO: faltam ${data.progress.missing} ID(s) neste lote!`, 'danger');
        // Redirect to embalagem page so user can handle missing items there
        window.location.href = '/expedicao/embalagem';
        return;
      }

      // separado_completo
      showAlert('doublecheck-alert', 'Separação completa! Gerando etiqueta...', 'success');
      // Redirect current tab to the label preview page.
      // Using window.location.href avoids popup blockers (window.open in async is blocked).
      if (data.label_url) {
        window.location.href = data.label_url;
      } else {
        window.location.href = '/expedicao/embalagem';
      }
    },
  };

  // ── EMBALA E FATURA ─────────────────────────────────────────
  const Embalagem = {
    async embalar(loteId) {
      const { ok, data } = await postJson('/expedicao/api/embalagem/embalar', { lote_id: loteId });
      if (!ok) {
        showAlert('embalagem-alert', data.error || 'Erro ao embalar lote.', 'danger');
        return;
      }
      showAlert('embalagem-alert', 'Lote embalado. Liberando prateleiras...', 'success');
      // If API returns any not-cleared positions, show them in console for operator
      if (data && data.not_cleared_positions) console.warn('not_cleared_positions', data.not_cleared_positions);
      // Stay on Embala e Fatura page until the lote is faturado
      window.location.href = '/expedicao/embalagem';
    },

    async faturar(loteId) {
      const { ok, data } = await postJson('/expedicao/api/embalagem/faturar', { lote_id: loteId });
      if (!ok) {
        showAlert('embalagem-alert', data.error || 'Erro ao enviar para faturamento.', 'danger');
        return;
      }
      showAlert('embalagem-alert', 'Lote faturado. Liberando prateleiras...', 'success');
      if (data && data.not_cleared_positions) console.warn('not_cleared_positions', data.not_cleared_positions);
      window.location.href = '/expedicao/checkin';
    },
  };

  return { Checkin, Picking, Doublecheck, Embalagem };
})();
