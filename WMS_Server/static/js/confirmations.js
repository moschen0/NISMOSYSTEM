/**
 * CONFIRMATIONS.JS — Lógica de Conferência de OS
 * Padrão MVC: Model (API) + View (DOM) + Controller (Lógica)
 */

const Confirmations = (() => {
  // Estado interno
  let sessionHistory = [];
  let currentUser = '';
  let currentSector = '';
  let stats = { total: 0, ok: 0, error: 0, accuracy_percent: 0 };

  // ── INICIALIZAÇÃO ────────────────────────────────────────────
  function init(username, sector) {
    currentUser = username;
    currentSector = sector;
    setupEventListeners();
    
    // Tenta carregar stats após delay
    setTimeout(() => {
      const fieldA = document.getElementById('field-a');
      if (fieldA) fieldA.focus();
    }, 100);
    
    // Carrega stats com delay
    setTimeout(() => {
      loadStats();
    }, 500);
  }

  // ── SETUP ────────────────────────────────────────────────────
  function setupEventListeners() {
    const fieldA = document.getElementById('field-a');
    const fieldB = document.getElementById('field-b');

    // Enter em field-a vai para field-b
    fieldA.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        fieldB.focus();
      }
    });

    // Enter em field-b confirma
    fieldB.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        doComparar();
      }
    });
  }

  // ── COMPARAÇÃO ───────────────────────────────────────────────
  function doComparar() {
    const fieldA = document.getElementById('field-a');
    const fieldB = document.getElementById('field-b');
    const osA = fieldA.value.trim();
    const osB = fieldB.value.trim();

    if (!osA || !osB) {
      flashEmpty();
      return;
    }

    // Determina resultado
    const ok = osA === osB;
    const result = ok ? 'ok' : 'error';

    // Marca campos visualmente
    markFields(ok);
    showResultBadge(ok, osA);

    // Salva no banco
    saveConfirmation(osA, osB, result, ok);
  }

  // ── FEEDBACK VISUAL ──────────────────────────────────────────
  function markFields(ok) {
    const fieldA = document.getElementById('field-a');
    const fieldB = document.getElementById('field-b');

    if (!fieldA || !fieldB) return;

    fieldA.classList.remove('match', 'mismatch');
    fieldB.classList.remove('match', 'mismatch');

    if (ok) {
      fieldA.classList.add('match');
      fieldB.classList.add('match');
    } else {
      fieldA.classList.add('mismatch');
      fieldB.classList.add('mismatch');
      // Anima shake
      fieldA.style.animation = 'none';
      fieldB.style.animation = 'none';
      setTimeout(() => {
        fieldA.style.animation = 'shake 0.5s';
        fieldB.style.animation = 'shake 0.5s';
      }, 10);
    }
  }

  function showResultBadge(ok, osA) {
    const badge = document.getElementById('result-badge');
    const message = document.getElementById('result-message');

    if (!badge || !message) {
      console.warn('Elementos result-badge ou result-message não encontrados');
      return;
    }

    if (ok) {
      badge.className = 'alert alert-success';
      message.innerHTML = `<i class="bi bi-check-circle"></i> <strong>✓ OS ${osA}</strong> conferida com sucesso!`;
    } else {
      badge.className = 'alert alert-danger';
      message.innerHTML = `<i class="bi bi-exclamation-circle"></i> <strong>✗ Divergência detectada</strong> — verifique os valores`;
    }

    badge.style.display = 'block';
    
    // Auto-limpar em 3s se OK
    if (ok) {
      setTimeout(() => {
        clearFields();
      }, 1600);
    }
  }

  function flashEmpty() {
    const fieldA = document.getElementById('field-a');
    const fieldB = document.getElementById('field-b');

    if (!fieldA || !fieldB) return;

    if (!fieldA.value) {
      fieldA.classList.add('mismatch');
      setTimeout(() => fieldA.classList.remove('mismatch'), 700);
    }
    if (!fieldB.value) {
      fieldB.classList.add('mismatch');
      setTimeout(() => fieldB.classList.remove('mismatch'), 700);
    }
  }

  // ── ÁUDIO (Bipes) ────────────────────────────────────────────
  function playSound(type) {
    try {
      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      const now = audioContext.currentTime;

      if (type === 'ok') {
        // Bipe ascendente (sucesso): 800Hz -> 1200Hz
        playTone(audioContext, 800, now, 0.1);
        playTone(audioContext, 1200, now + 0.15, 0.1);
      } else if (type === 'error') {
        // Bipe grave (erro): 300Hz -> 100Hz
        playTone(audioContext, 300, now, 0.15);
        playTone(audioContext, 100, now + 0.15, 0.15);
      }
    } catch (e) {
      console.warn('Áudio não disponível:', e);
    }
  }

  function playTone(audioContext, frequency, startTime, duration) {
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();

    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);

    oscillator.frequency.value = frequency;
    gainNode.gain.setValueAtTime(0.3, startTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, startTime + duration);

    oscillator.start(startTime);
    oscillator.stop(startTime + duration);
  }

  // ── PERSISTÊNCIA (API) ───────────────────────────────────────
  function saveConfirmation(osA, osB, result, ok) {
    fetch('/api/confirmations', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        os_reference: osA,
        os_confirmation: osB,
      }),
    })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        const confirmation = data.confirmation;

        // Adiciona ao histórico local
        sessionHistory.unshift({
          username: currentUser,
          os_reference: osA,
          os_confirmation: osB,
          result: result,
          data: confirmation.data,
          hora: confirmation.hora,
        });

        // Atualiza UI
        renderHistory();
        loadStats();

        // Som
        playSound(ok ? 'ok' : 'error');

        // Comportamento após resultado
        if (ok) {
          // Limpa após 1.6s
          setTimeout(() => {
            clearFields();
            document.getElementById('field-a').focus();
          }, 1600);
        } else {
          // Mostra modal de erro
          showModalErro(osA, osB);
        }
      } else {
        console.error('Erro ao salvar:', data.error);
      }
    })
    .catch(error => console.error('Erro na API:', error));
  }

  // ── HISTÓRICO ────────────────────────────────────────────────
  function renderHistory() {
    const list = document.getElementById('history-list');
    if (!list) return;

    if (sessionHistory.length === 0) {
      list.innerHTML = `
        <div class="text-center text-muted p-4 small">
          <i class="bi bi-inbox"></i> Nenhuma conferência realizada ainda
        </div>
      `;
      return;
    }

    list.innerHTML = sessionHistory.map((h, i) => `
      <div class="history-item">
        <div class="history-main">
          <span class="history-os">OS ${h.os_reference}</span>
          <span class="history-meta">${h.username || currentUser} • ${currentSector}</span>
          <span class="history-time">${h.data} ${h.hora}</span>
        </div>
        <span class="badge-resultado ${h.result === 'ok' ? 'badge-ok' : 'badge-erro'}">
          ${h.result === 'ok' ? '✓ OK' : '✗ Divergente'}
        </span>
      </div>
    `).join('');
  }

  // ── ESTATÍSTICAS ─────────────────────────────────────────────
  function loadStats() {
    fetch('/api/confirmations/stats')
      .then(response => {
        if (!response.ok) {
          console.warn('Erro ao carregar stats:', response.status);
          return {};
        }
        return response.json();
      })
      .then(data => {
        if (data && data.stats) {
          stats = data.stats;
          updateStatsUI();
        }
      })
      .catch(error => console.error('Erro ao carregar stats:', error));
  }

  function updateStatsUI() {
    const totalEl = document.getElementById('stat-total');
    const okEl = document.getElementById('stat-ok');
    const errorEl = document.getElementById('stat-error');
    const accuracyEl = document.getElementById('stat-accuracy');
    
    if (totalEl) totalEl.textContent = stats.total;
    if (okEl) okEl.textContent = stats.ok;
    if (errorEl) errorEl.textContent = stats.error;
    if (accuracyEl) accuracyEl.textContent = stats.accuracy_percent.toFixed(1) + '%';
  }

  // ── MODAL DE ERRO ────────────────────────────────────────────
  function showModalErro(osA, osB) {
    const aEl = document.getElementById('modal-os-a');
    const bEl = document.getElementById('modal-os-b');
    const modalEl = document.getElementById('modalErro');

    if (aEl) aEl.textContent = osA;
    if (bEl) bEl.textContent = osB;

    if (modalEl && typeof bootstrap !== 'undefined') {
      const modal = new bootstrap.Modal(modalEl);
      modal.show();
    }
  }

  function fecharModalErro() {
    clearFields();
    const fieldA = document.getElementById('field-a');
    if (fieldA) fieldA.focus();
  }

  // ── LIMPEZA ──────────────────────────────────────────────────
  function clearFields() {
    const fieldA = document.getElementById('field-a');
    const fieldB = document.getElementById('field-b');
    const badge = document.getElementById('result-badge');

    if (fieldA) {
      fieldA.value = '';
      fieldA.classList.remove('match', 'mismatch');
    }
    if (fieldB) {
      fieldB.value = '';
      fieldB.classList.remove('match', 'mismatch');
    }
    if (badge) {
      badge.style.display = 'none';
    }
  }

  // ── EXPORTAÇÃO ───────────────────────────────────────────────
  function exportarRegistros() {
    fetch('/api/confirmations/export', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    })
    .then(response => {
      if (!response.ok) {
        return response.json().then(data => {
          throw new Error(data.error || 'Erro ao exportar');
        });
      }
      // O servidor envia o arquivo diretamente
      return response.blob().then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `confirmacoes_os_${new Date().toISOString().slice(0,10)}.xlsx`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      });
    })
    .catch(error => {
      console.error('Erro ao exportar:', error);
      alert('Erro ao exportar registros: ' + error.message);
    });
  }

  // ── INTERFACE PÚBLICA ────────────────────────────────────────
  return {
    init: init,
    doComparar: doComparar,
    exportarRegistros: exportarRegistros,
    fecharModalErro: fecharModalErro,
    playSound: playSound,
  };
})();
