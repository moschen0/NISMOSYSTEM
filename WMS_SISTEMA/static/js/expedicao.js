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

  function showCheckinBlockModal(message) {
    const modalEl = document.getElementById('checkin-block-modal');
    const messageEl = document.getElementById('checkin-block-modal-message');
    if (!modalEl || !messageEl || !window.bootstrap) {
      showAlert('checkin-alert', message, 'danger');
      return;
    }
    messageEl.textContent = message;
    const modal = window.bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
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
      const text = await response.text();
      data = text ? JSON.parse(text) : {};
    } catch (e) {
      data = {};
    }
    return { ok: response.ok, status: response.status, data };
  }

  // ── CHECKIN DE ENTRADA ──────────────────────────────────────
  const Checkin = {
    applyPendingSuggestedEndereco() {
      let pending = null;
      try {
        pending = JSON.parse(sessionStorage.getItem('expedicaoCheckinSuggestedEndereco') || 'null');
      } catch (e) {
        pending = null;
      }
      if (!pending || !pending.loteId || !pending.endereco) return;

      const enderecoEl = document.getElementById(`endereco-${pending.loteId}`);
      if (enderecoEl && !enderecoEl.value) {
        enderecoEl.value = pending.endereco;
      }
      sessionStorage.removeItem('expedicaoCheckinSuggestedEndereco');
    },

    upsertLoteCard(lote, items, suggestedEndereco) {
      if (!lote || !lote.id) return false;

      const container = document.getElementById('open-lotes-container');
      if (!container) return false;

      const empty = document.getElementById('open-lotes-empty');
      if (empty) empty.remove();

      let card = document.querySelector(`[data-lote-id="${lote.id}"]`);
      if (!card) {
        card = document.createElement('div');
        card.className = 'border rounded p-3 mb-3';
        card.dataset.loteId = lote.id;
        container.prepend(card);
      }

      const enderecoValue = lote.endereco || suggestedEndereco || '';
      const itemRows = (items || []).map((item) => (
        `<li class="list-group-item px-0 py-1 font-monospace">${item.order_id || ''}</li>`
      )).join('');

      card.innerHTML = `
        <div class="d-flex justify-content-between align-items-center mb-2">
          <strong class="font-monospace">${lote.lote_code || ''}</strong>
          <span class="badge bg-info">Cliente ${lote.client_number || ''}</span>
        </div>
        <ul class="list-group list-group-flush mb-2">${itemRows}</ul>
        <div class="input-group">
          <input type="text" class="form-control form-control-sm" id="endereco-${lote.id}" placeholder="Endereçamento (ex: A01)" value="${enderecoValue}">
          <button class="btn btn-sm btn-success" onclick="Expedicao.Checkin.fechar(${lote.id})">
            <i class="bi bi-lock"></i> Fechar Lote
          </button>
        </div>`;

      return true;
    },

    init() {
      Checkin.applyPendingSuggestedEndereco();

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

      const { ok, status, data } = await postJson('/expedicao/api/checkin/scan', {
        order_id: orderId,
        client_number: clientNumber,
      });

      if (!ok) {
        const errorMessage = data.error || data.message || (status === 409
          ? 'Este ID Master já foi processado e não pode retornar ao Checkin de Entrada.'
          : 'Erro ao bipar ID Master.');
        if (data.needs_client_number) {
          const clientWrapper = document.getElementById('client-number-wrapper');
          if (clientWrapper) clientWrapper.style.display = 'block';
        }
        showAlert('checkin-alert', errorMessage, 'danger');
        if (status === 409) {
          showCheckinBlockModal(errorMessage);
        }
        masterInput.focus();
        masterInput.select();
        return;
      }

      masterInput.value = '';
      if (clientInput) clientInput.value = '';
      if (data.suggested_endereco && data.lote && data.lote.id) {
        sessionStorage.setItem('expedicaoCheckinSuggestedEndereco', JSON.stringify({
          loteId: data.lote.id,
          endereco: data.suggested_endereco,
        }));
      }
      window.location.reload();
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
      const { ok, data } = await postJson('/expedicao/api/picking/gerar-onda', { horario });
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
      this._updateProgressBar();
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
      this._updateFinalizeButton(confirmed, total);
    },

    _updateFinalizeButton(confirmed, total) {
      const finalizeBtn = document.getElementById('dc-finalizar-btn');
      const finalizeMissingBtn = document.getElementById('dc-finalizar-falta-btn');
      const isComplete = total > 0 && confirmed >= total;
      if (finalizeBtn) finalizeBtn.style.display = isComplete ? 'block' : 'none';
      if (finalizeMissingBtn) finalizeMissingBtn.style.display = total > 0 && !isComplete ? 'block' : 'none';
    },

    openLeaderAuthModal() {
      const modalEl = document.getElementById('dcLeaderAuthModal');
      if (!modalEl || !window.bootstrap) return;
      const alertEl = document.getElementById('dc-leader-auth-alert');
      if (alertEl) alertEl.style.display = 'none';
      const usernameInput = document.getElementById('dc-leader-username');
      const passwordInput = document.getElementById('dc-leader-password');
      if (usernameInput) usernameInput.value = '';
      if (passwordInput) passwordInput.value = '';
      const modal = window.bootstrap.Modal.getOrCreateInstance(modalEl);
      modal.show();
      setTimeout(() => { if (usernameInput) usernameInput.focus(); }, 250);
    },

    async finalizarComFalta() {
      const username = document.getElementById('dc-leader-username').value.trim();
      const password = document.getElementById('dc-leader-password').value;
      await this.finalizar({ leaderUsername: username, leaderPassword: password });
    },

    _formatPrintDateTime(date) {
      const pad = (value) => String(value).padStart(2, '0');
      return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
    },

    _updateLabelPrintedAt() {
      const printedAtEl = document.getElementById('dcLabelPrintedAt');
      if (printedAtEl) {
        printedAtEl.textContent = this._formatPrintDateTime(new Date()).toUpperCase();
      }
    },

    printLabel() {
      this._updateLabelPrintedAt();
      window.print();
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
      }

      if (!ok || data.result === 'nao_pertence') {
        // show a very loud warning overlay on doublecheck page
        const msg = data.message || data.error || 'OS não pertence a este lote ou não existe!';
        showLoudWarning(msg);
        return;
      }

      showAlert('doublecheck-alert', 'ID confirmado.', 'success');
    },

    async finalizar(auth) {
      const loteId = document.getElementById('dc-lote-id').value;
      const payload = { lote_id: parseInt(loteId, 10) };
      if (auth) {
        payload.leader_username = auth.leaderUsername || '';
        payload.leader_password = auth.leaderPassword || '';
      }
      const { ok, data } = await postJson('/expedicao/api/doublecheck/finalizar', {
        ...payload,
      });
      if (!ok) {
        if (data.needs_leader_auth) {
          const alertEl = document.getElementById('dc-leader-auth-alert');
          if (alertEl) {
            alertEl.className = 'alert alert-danger';
            alertEl.textContent = data.error || 'Autorização do líder obrigatória.';
            alertEl.style.display = 'block';
            return;
          }
          this.openLeaderAuthModal();
          return;
        }
        showAlert('doublecheck-alert', data.error || 'Erro ao finalizar separação.', 'danger');
        return;
      }
      // Notify user about status
      if (data.status === 'separado_com_falta') {
        const modalEl = document.getElementById('dcLeaderAuthModal');
        if (modalEl && window.bootstrap) window.bootstrap.Modal.getOrCreateInstance(modalEl).hide();
        showAlert('doublecheck-alert', `Finalizado com falta por ${data.authorized_by || 'líder autorizado'}. Faltam ${data.progress.missing} ID(s).`, 'warning');
        // Redirect to embalagem page so user can handle missing items there
        window.location.href = '/expedicao/embalagem';
        return;
      }

      // separado_completo
      showAlert('doublecheck-alert', 'Separação completa! Gerando etiqueta...', 'success');
      // separado_completo — show the expedition label as a modal on this page
      showAlert('doublecheck-alert', 'Separação completa! Etiqueta gerada.', 'success');

      const ld = data.label_data;
      if (ld) {
        const modalBg = document.getElementById('dcLabelModalBg');
        if (modalBg) {
          const codigo = (ld.cliente_codigo || '').toString();
          const cnpjCpf = ld.cliente_cnpj_cpf ? `CNPJ/CPF ${ld.cliente_cnpj_cpf}` : 'CNPJ/CPF —';
          const cidadeUf = [ld.cliente_cidade, ld.cliente_estado].filter(Boolean).join('  ');
          const setor = ld.cliente_setor ? ` SETOR: ${ld.cliente_setor}` : '';
          const rota = ld.cliente_rota ? `-ROTA ${ld.cliente_rota}` : '';
          const entrada = (ld.usuario_entrada || '—').toString().toUpperCase();
          const embalagem = (ld.usuario_embalagem || '—').toString().toUpperCase();

          document.getElementById('dcLabelCode').textContent = codigo.toUpperCase();
          document.getElementById('dcLabelCnpjCpf').textContent = cnpjCpf.toUpperCase();
          document.getElementById('dcLabelName').textContent = (ld.cliente_nome || '—').toUpperCase();
          document.getElementById('dcLabelAddress').textContent = (ld.cliente_endereco || '—').toUpperCase();
          document.getElementById('dcLabelCityState').textContent = (cidadeUf || '—').toUpperCase();
          document.getElementById('dcLabelCepRota').textContent = (`${ld.cliente_cep || ''}${setor}${rota}`.trim() || '—').toUpperCase();
          document.getElementById('dcLabelEntrada').textContent = `ENTRADA ${entrada}`;
          document.getElementById('dcLabelMeta').innerHTML = `EMBALAGEM ${embalagem}  IMPRESSO <span id="dcLabelPrintedAt">—</span>`;
          modalBg.classList.add('active');
          return; // stay on this page; user clicks Continue or Print
        }
      }
      // fallback if modal elements not found (e.g. on a different page)
      window.location.href = '/expedicao/embalagem';
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
