// ═══════════════════════════════════════════════════════════
// College Library Management System – Client-Side JavaScript
// ═══════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', function () {

    // ── Sidebar Toggle (Admin) ──
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');
    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', function () {
            // On mobile, use show-mobile class
            if (window.innerWidth <= 768) {
                sidebar.classList.toggle('show-mobile');
            } else {
                sidebar.classList.toggle('collapsed');
            }
        });
    }

    // ── Client-Side Table Search / Filter ──
    initTableSearch('booksTable', 'tableSearchInput');
    initTableSearch('studentsTable', 'tableSearchInput');
    initTableSearch('transactionsTable', 'tableSearchInput');
    initTableSearch('historyTable', 'tableSearchInput');
    initTableSearch('recentTable', 'tableSearchInput');

    // Generic live-search for any table
    function initTableSearch(tableId, inputId) {
        // Also support the inline JS search boxes
        const table = document.getElementById(tableId);
        if (!table) return;

        // If there's no dedicated input, create a small one above the table
        let input = document.getElementById(inputId);
        if (!input) {
            // Check if we already added one
            if (table.parentElement.querySelector('.js-table-search')) return;

            const searchDiv = document.createElement('div');
            searchDiv.className = 'p-3 border-bottom js-table-search';
            searchDiv.innerHTML = `
                <div class="input-group input-group-sm">
                    <span class="input-group-text"><i class="bi bi-filter"></i></span>
                    <input type="text" class="form-control"
                           placeholder="Quick filter this table…" id="jsSearch_${tableId}">
                </div>
            `;
            table.parentElement.insertBefore(searchDiv, table);
            input = document.getElementById(`jsSearch_${tableId}`);
        }

        if (!input) return;

        input.addEventListener('keyup', function () {
            const filter = this.value.toLowerCase();
            const rows = table.querySelectorAll('tbody tr');
            rows.forEach(function (row) {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(filter) ? '' : 'none';
            });
        });
    }

    // ── Auto-dismiss alerts after 5 seconds ──
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function (alert) {
        setTimeout(function () {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            bsAlert.close();
        }, 5000);
    });

    // ── Confirm delete modals (fallback for forms without onclick) ──
    document.querySelectorAll('.delete-form').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            if (!confirm('Are you sure you want to delete this item?')) {
                e.preventDefault();
            }
        });
    });

    // ── Book QR Code Modal Event Listeners ──
    document.querySelectorAll('.btn-qr-code').forEach(function (btn) {
        btn.addEventListener('click', function () {
            const id = this.dataset.id;
            const title = this.dataset.title;
            const author = this.dataset.author;
            const isbn = this.dataset.isbn;
            const category = this.dataset.category;
            const qrUrl = this.dataset.qr;
            const viewUrl = this.dataset.viewUrl;

            const modalTitle = document.getElementById('modalBookTitle');
            const modalAuthor = document.getElementById('modalBookAuthor');
            const modalCategory = document.getElementById('modalBookCategory');
            const modalBookId = document.getElementById('modalBookId');
            const modalIsbn = document.getElementById('modalBookIsbn');
            const modalImg = document.getElementById('modalQrImage');
            const downloadBtn = document.getElementById('downloadQrBtn');
            const viewFullPageBtn = document.getElementById('viewFullPageBtn');

            if (modalTitle) modalTitle.textContent = title;
            if (modalAuthor) modalAuthor.textContent = author.startsWith('by ') ? author : `by ${author}`;
            if (modalCategory) modalCategory.textContent = category;
            if (modalBookId) modalBookId.textContent = id;
            if (modalIsbn) modalIsbn.textContent = isbn;
            if (modalImg) modalImg.src = qrUrl;
            if (downloadBtn) {
                downloadBtn.href = qrUrl + '?download=1';
                downloadBtn.download = `book_${id}_qr.png`;
            }
            if (viewFullPageBtn && viewUrl) {
                viewFullPageBtn.href = viewUrl;
            }

            const qrModal = new bootstrap.Modal(document.getElementById('qrModal'));
            qrModal.show();
        });
    });


    const printBtn = document.getElementById('printQrBtn');
    if (printBtn) {
        printBtn.addEventListener('click', printQRCode);
    }

    // ── Admin QR Scanner Page Logic ──
    const readerDiv = document.getElementById('reader');
    if (readerDiv && typeof Html5Qrcode !== 'undefined') {
        let html5QrcodeScanner = new Html5Qrcode("reader");
        let isScanning = false;

        function startCamera() {
            Html5Qrcode.getCameras().then(cameras => {
                if (cameras && cameras.length) {
                    const cameraId = cameras[0].id;
                    html5QrcodeScanner.start(
                        { facingMode: "environment" },
                        { fps: 10, qrbox: { width: 220, height: 220 } },
                        (decodedText, decodedResult) => {
                            // On successful scan
                            playBeepSound();
                            lookupBookByQR(decodedText);
                        },
                        (errorMessage) => {
                            // ignore parse errors
                        }
                    ).then(() => {
                        isScanning = true;
                    }).catch(err => {
                        readerDiv.innerHTML = `
                            <div class="alert alert-warning m-0">
                                <i class="bi bi-camera-video-off me-2"></i>Camera access unavailable. Use <strong>Upload QR Image</strong> or <strong>Manual Search</strong>.
                            </div>`;
                    });
                } else {
                    readerDiv.innerHTML = `
                        <div class="alert alert-info m-0">
                            <i class="bi bi-info-circle me-2"></i>No camera detected. Please upload a QR code image or search manually.
                        </div>`;
                }
            }).catch(err => {
                readerDiv.innerHTML = `
                    <div class="alert alert-warning m-0">
                        <i class="bi bi-camera-video-off me-2"></i>Camera permissions required or not supported in current browser context.
                    </div>`;
            });
        }

        startCamera();

        const toggleBtn = document.getElementById('toggleCameraBtn');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', function () {
                if (isScanning) {
                    html5QrcodeScanner.stop().then(() => {
                        isScanning = false;
                        startCamera();
                    });
                } else {
                    startCamera();
                }
            });
        }

        // Handle File Upload Scan (Dual Engine: jsQR Canvas + Html5Qrcode Fallback)
        function decodeQRFileWithJsQR(imageFile) {
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = function(e) {
                    const img = new Image();
                    img.onload = function() {
                        try {
                            const canvas = document.createElement('canvas');
                            canvas.width = img.width;
                            canvas.height = img.height;
                            const ctx = canvas.getContext('2d');
                            ctx.drawImage(img, 0, 0, img.width, img.height);
                            const imageData = ctx.getImageData(0, 0, img.width, img.height);
                            if (typeof jsQR !== 'undefined') {
                                const code = jsQR(imageData.data, imageData.width, imageData.height);
                                if (code && code.data) {
                                    return resolve(code.data);
                                }
                            }
                            reject(new Error('jsQR could not find QR code in image'));
                        } catch (err) {
                            reject(err);
                        }
                    };
                    img.onerror = () => reject(new Error('Failed to load image file'));
                    img.src = e.target.result;
                };
                reader.onerror = () => reject(new Error('Failed to read image file'));
                reader.readAsDataURL(imageFile);
            });
        }

        const fileInput = document.getElementById('qrFileInput');
        if (fileInput) {
            fileInput.addEventListener('change', e => {
                if (e.target.files.length == 0) return;
                const imageFile = e.target.files[0];
                showScannerLoading();

                decodeQRFileWithJsQR(imageFile)
                    .then(decodedText => {
                        playBeepSound();
                        lookupBookByQR(decodedText);
                    })
                    .catch(() => {
                        // Engine 2 Fallback: Html5Qrcode standalone decoder
                        const decoderEl = document.getElementById('qr-file-decoder');
                        if (decoderEl && typeof Html5Qrcode !== 'undefined') {
                            const fileDecoder = new Html5Qrcode("qr-file-decoder");
                            fileDecoder.scanFile(imageFile, true)
                                .then(decodedText => {
                                    playBeepSound();
                                    lookupBookByQR(decodedText);
                                })
                                .catch(err => {
                                    showScannerError('Unable to read QR code from uploaded image. Please ensure image contains a clear, valid QR code.');
                                });
                        } else {
                            showScannerError('Unable to read QR code from uploaded image. Please ensure image contains a clear, valid QR code.');
                        }
                    });
            });
        }

        // Drag and Drop for Upload Tab
        const dropArea = document.getElementById('dropArea');
        if (dropArea) {
            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                dropArea.addEventListener(eventName, e => {
                    e.preventDefault();
                    e.stopPropagation();
                }, false);
            });
            dropArea.addEventListener('drop', e => {
                const dt = e.dataTransfer;
                const files = dt.files;
                if (files.length > 0) {
                    fileInput.files = files;
                    const event = new Event('change');
                    fileInput.dispatchEvent(event);
                }
            });
        }
    }

    // Manual Search Form Handler
    const manualForm = document.getElementById('manualSearchForm');
    if (manualForm) {
        manualForm.addEventListener('submit', function (e) {
            e.preventDefault();
            const query = document.getElementById('manualQuery').value;
            if (query) {
                lookupBookByQR(query);
            }
        });
    }

});

// Global Print QR Code Function
function printQRCode() {
    const titleEl = document.getElementById('modalBookTitle');
    const authorEl = document.getElementById('modalBookAuthor');
    const isbnEl = document.getElementById('modalBookIsbn');
    const bookIdEl = document.getElementById('modalBookId');
    const categoryEl = document.getElementById('modalBookCategory');
    const qrImgEl = document.getElementById('modalQrImage');

    if (!titleEl || !qrImgEl) return;

    const title = titleEl.textContent;
    const author = authorEl.textContent;
    const isbn = isbnEl.textContent;
    const bookId = bookIdEl ? bookIdEl.textContent : '';
    const category = categoryEl ? categoryEl.textContent : 'LIBRARY';
    const qrImgSrc = qrImgEl.src;

    const printWin = window.open('', '_blank', 'width=650,height=650');
    printWin.document.write(`
        <!DOCTYPE html>
        <html>
        <head>
            <title>Print Book QR Label - ${isbn}</title>
            <style>
                body { font-family: 'Segoe UI', Arial, sans-serif; text-align: center; padding: 20px; margin: 0; background-color: #fff; }
                .label-card { border: 2px dashed #111; padding: 20px; border-radius: 12px; display: inline-block; max-width: 320px; width: 100%; box-sizing: border-box; }
                .org-header { font-size: 12px; font-weight: 800; letter-spacing: 1px; color: #333; text-transform: uppercase; margin-bottom: 12px; border-bottom: 1px solid #ddd; padding-bottom: 6px; }
                .field-row { font-size: 13px; text-align: left; margin-bottom: 4px; color: #222; }
                .field-label { font-weight: bold; color: #555; display: inline-block; width: 90px; }
                .qr-image { width: 180px; height: 180px; margin: 12px auto; display: block; image-rendering: pixelated; }
                .book-id-badge { font-family: 'Courier New', monospace; font-size: 14px; font-weight: bold; background: #f0f0f0; padding: 6px 12px; border-radius: 6px; display: inline-block; color: #000; margin-top: 6px; border: 1px solid #ccc; }
                @media print {
                    body { padding: 0; background: none; }
                    .label-card { border: 2px solid #000; page-break-inside: avoid; }
                }
            </style>
        </head>
        <body>
            <div class="label-card">
                <div class="org-header">LIBRARY MANAGEMENT SYSTEM</div>
                <div class="field-row"><span class="field-label">Book Name:</span> <strong>${title}</strong></div>
                <div class="field-row"><span class="field-label">ISBN:</span> <code>${isbn}</code></div>
                <div class="field-row"><span class="field-label">Author:</span> ${author}</div>
                <img src="${qrImgSrc}" class="qr-image" onload="window.print(); window.close();" />
                <div class="book-id-badge">Book ID: ${bookId}</div>
            </div>
        </body>
        </html>
    `);
    printWin.document.close();
}


// Global State for Scanner & Issue Workflow
let currentScannedBook = null;
let currentVerifiedStudent = null;
let isLookupInProgress = false;

// Helper to get CSRF Token from DOM meta tag
function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

// Safe JSON Response Helper Function
async function parseJsonResponse(res) {
    const contentType = res.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
        const text = await res.text();
        if (res.status === 401 || res.status === 403) {
            throw new Error('Authentication required or session expired. Please log in.');
        }
        if (res.status === 404) {
            throw new Error('Requested book or endpoint not found (404).');
        }
        throw new Error(`Server returned non-JSON response (${res.status}). Please check API URL or login state.`);
    }
    return await res.json();
}

// Global Lookup Book Function for Scanner
function lookupBookByQR(qrCodeData) {
    if (isLookupInProgress) return;
    isLookupInProgress = true;

    showScannerLoading();
    resetIssueForm();

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 8000);

    fetch('/admin/api/lookup-book', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({ qr_code: qrCodeData }),
        signal: controller.signal
    })
    .then(parseJsonResponse)
    .then(data => {
        clearTimeout(timeoutId);
        if (data.success && data.book) {
            currentScannedBook = data.book;
            showScannerBookResult(data.book);
        } else {
            currentScannedBook = null;
            showScannerError(data.message || data.error || 'Book not found.');
        }
    })
    .catch(err => {
        clearTimeout(timeoutId);
        currentScannedBook = null;
        if (err.name === 'AbortError') {
            showScannerError('Request timed out. Please try scanning or searching again.');
        } else {
            showScannerError(err.message || 'Error communicating with server. Please try again.');
        }
    })
    .finally(() => {
        isLookupInProgress = false;
    });
}

function showScannerLoading() {
    const emptyState = document.getElementById('emptyState');
    const loadingState = document.getElementById('loadingState');
    const bookFoundState = document.getElementById('bookFoundState');
    const errorState = document.getElementById('errorState');

    if (emptyState) emptyState.classList.add('d-none');
    if (bookFoundState) bookFoundState.classList.add('d-none');
    if (errorState) errorState.classList.add('d-none');
    if (loadingState) loadingState.classList.remove('d-none');
}

function showScannerBookResult(book) {
    const loadingState = document.getElementById('loadingState');
    const bookFoundState = document.getElementById('bookFoundState');
    const errorState = document.getElementById('errorState');

    if (loadingState) loadingState.classList.add('d-none');
    if (errorState) errorState.classList.add('d-none');
    if (bookFoundState) bookFoundState.classList.remove('d-none');

    document.getElementById('resTitle').textContent = book.title;
    document.getElementById('resAuthor').textContent = `by ${book.author}`;
    document.getElementById('resCategory').textContent = book.category;
    document.getElementById('resIsbn').textContent = book.isbn;
    document.getElementById('resAvailable').textContent = book.available_copies;
    document.getElementById('resTotal').textContent = book.total_copies;

    const resBookId = document.getElementById('resBookId');
    if (resBookId) resBookId.textContent = book.id;

    const resIssued = document.getElementById('resIssued');
    if (resIssued) resIssued.textContent = Math.max(0, book.total_copies - book.available_copies);

    const resPublisher = document.getElementById('resPublisher');
    if (resPublisher) resPublisher.textContent = book.publisher || '-';

    const resYear = document.getElementById('resYear');
    if (resYear) resYear.textContent = book.year || '-';

    const resDescription = document.getElementById('resDescription');
    if (resDescription) resDescription.textContent = book.description || 'No description provided.';

    const statusBadge = document.getElementById('resStatusBadge');
    if (statusBadge) {
        if (book.available_copies > 0) {
            statusBadge.className = 'badge bg-success';
            statusBadge.textContent = 'Available';
        } else {
            statusBadge.className = 'badge bg-danger';
            statusBadge.textContent = 'No copies available';
        }
    }

    const issueBtn = document.getElementById('resIssueBtn');
    if (issueBtn) {
        if (book.available_copies <= 0) {
            issueBtn.classList.add('disabled');
            issueBtn.disabled = true;
            issueBtn.innerHTML = '<i class="bi bi-x-circle me-1"></i> No Copies Available';
        } else {
            issueBtn.classList.remove('disabled');
            issueBtn.disabled = false;
            issueBtn.innerHTML = '<i class="bi bi-box-arrow-right me-1"></i> Issue This Book';
        }
    }

    const qrDlBtn = document.getElementById('resQrDownloadBtn');
    if (qrDlBtn) {
        qrDlBtn.href = book.qrcode_url;
        qrDlBtn.download = `QR_${book.isbn}.png`;
    }

    const editBtn = document.getElementById('resEditBtn');
    if (editBtn) {
        editBtn.href = book.edit_url;
    }

    // Handle Active Issues
    const activeSection = document.getElementById('resActiveIssuesSection');
    const activeList = document.getElementById('resActiveIssuesList');
    if (activeSection && activeList) {
        if (book.active_issues && book.active_issues.length > 0) {
            activeSection.classList.remove('d-none');
            activeList.innerHTML = book.active_issues.map(iss => `
                <div class="list-group-item d-flex justify-content-between align-items-center bg-light">
                    <div>
                        <strong class="text-dark">${iss.student_name}</strong>
                        <small class="text-muted d-block">Roll: ${iss.student_id} | Due: ${iss.due_date}</small>
                    </div>
                    <div>
                        <span class="badge ${iss.status === 'overdue' ? 'bg-danger' : 'bg-primary'} me-2">${iss.status}</span>
                        <form method="POST" action="/admin/return/${iss.transaction_id}" style="display:inline;">
                            <button type="submit" class="btn btn-sm btn-outline-success">Return</button>
                        </form>
                    </div>
                </div>
            `).join('');
        } else {
            activeSection.classList.add('d-none');
            activeList.innerHTML = '';
        }
    }
}

function showScannerError(msg) {
    const loadingState = document.getElementById('loadingState');
    const bookFoundState = document.getElementById('bookFoundState');
    const errorState = document.getElementById('errorState');
    const errorMsg = document.getElementById('errorMessage');

    if (loadingState) loadingState.classList.add('d-none');
    if (bookFoundState) bookFoundState.classList.add('d-none');
    if (errorState) errorState.classList.remove('d-none');
    if (errorMsg) errorMsg.textContent = msg;
}

function resetScannerResult() {
    currentScannedBook = null;
    currentVerifiedStudent = null;

    const emptyState = document.getElementById('emptyState');
    const loadingState = document.getElementById('loadingState');
    const bookFoundState = document.getElementById('bookFoundState');
    const errorState = document.getElementById('errorState');

    if (loadingState) loadingState.classList.add('d-none');
    if (bookFoundState) bookFoundState.classList.add('d-none');
    if (errorState) errorState.classList.add('d-none');
    if (emptyState) emptyState.classList.remove('d-none');

    resetIssueForm();
}

function resetIssueForm() {
    currentVerifiedStudent = null;
    const issueSection = document.getElementById('qrIssueSection');
    const alertBox = document.getElementById('qrIssueAlert');
    const matchedCard = document.getElementById('studentMatchedCard');
    const rollInput = document.getElementById('studentRollInput');
    const confirmBtn = document.getElementById('btnConfirmIssue');

    if (issueSection) issueSection.classList.add('d-none');
    if (alertBox) {
        alertBox.classList.add('d-none');
        alertBox.className = 'alert d-none py-2 px-3 mb-3 small';
        alertBox.textContent = '';
    }
    if (matchedCard) matchedCard.classList.add('d-none');
    if (rollInput) rollInput.value = '';
    if (confirmBtn) confirmBtn.disabled = true;
}

// ── Interactive QR Scanner Issue Book Event Handlers ──
document.addEventListener('DOMContentLoaded', function() {
    const resIssueBtn = document.getElementById('resIssueBtn');
    const qrIssueSection = document.getElementById('qrIssueSection');
    const btnLookupStudent = document.getElementById('btnLookupStudent');
    const studentRollInput = document.getElementById('studentRollInput');
    const btnConfirmIssue = document.getElementById('btnConfirmIssue');
    const btnCancelIssue = document.getElementById('btnCancelIssue');
    const btnCloseIssueSection = document.getElementById('btnCloseIssueSection');
    const qrIssueAlert = document.getElementById('qrIssueAlert');
    const studentMatchedCard = document.getElementById('studentMatchedCard');

    if (resIssueBtn) {
        resIssueBtn.addEventListener('click', function() {
            if (!currentScannedBook) return;
            if (currentScannedBook.available_copies <= 0) {
                showIssueAlert('danger', 'No available copies of this book to issue.');
                return;
            }
            if (qrIssueSection) {
                qrIssueSection.classList.remove('d-none');
                if (studentRollInput) studentRollInput.focus();
            }
        });
    }

    if (btnLookupStudent) {
        btnLookupStudent.addEventListener('click', performStudentLookup);
    }

    if (studentRollInput) {
        studentRollInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                performStudentLookup();
            }
        });
    }

    function performStudentLookup() {
        const roll = studentRollInput ? studentRollInput.value.trim() : '';
        if (!roll) {
            showIssueAlert('warning', 'Please enter a Student Roll Number / ID.');
            if (studentMatchedCard) studentMatchedCard.classList.add('d-none');
            if (btnConfirmIssue) btnConfirmIssue.disabled = true;
            return;
        }

        fetch('/admin/api/lookup-student', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ student_id: roll })
        })
        .then(parseJsonResponse)
        .then(data => {
            if (data.success && data.student) {
                currentVerifiedStudent = data.student;
                document.getElementById('stuMatchedName').textContent = data.student.name;
                document.getElementById('stuMatchedRoll').textContent = data.student.student_id;
                document.getElementById('stuMatchedDept').textContent = data.student.department;
                document.getElementById('stuMatchedYear').textContent = `Year ${data.student.year}`;
                document.getElementById('stuMatchedActiveCount').textContent = data.student.active_issues_count;

                if (studentMatchedCard) studentMatchedCard.classList.remove('d-none');

                if (data.student.can_issue) {
                    showIssueAlert('success', `Student "${data.student.name}" verified! Click "Confirm Issue" to proceed.`);
                    if (btnConfirmIssue) btnConfirmIssue.disabled = false;
                } else {
                    showIssueAlert('danger', data.student.message || 'Student cannot borrow more books.');
                    if (btnConfirmIssue) btnConfirmIssue.disabled = true;
                }
            } else {
                currentVerifiedStudent = null;
                if (studentMatchedCard) studentMatchedCard.classList.add('d-none');
                if (btnConfirmIssue) btnConfirmIssue.disabled = true;
                showIssueAlert('danger', data.message || data.error || `Student with Roll Number "${roll}" not found.`);
            }
        })
        .catch(err => {
            currentVerifiedStudent = null;
            if (studentMatchedCard) studentMatchedCard.classList.add('d-none');
            if (btnConfirmIssue) btnConfirmIssue.disabled = true;
            showIssueAlert('danger', err.message || 'Error checking student roll number.');
        });
    }

    if (btnConfirmIssue) {
        btnConfirmIssue.addEventListener('click', function() {
            if (!currentScannedBook || !currentVerifiedStudent) {
                showIssueAlert('warning', 'Please select a valid book and verify student details first.');
                return;
            }

            btnConfirmIssue.disabled = true;
            btnConfirmIssue.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Processing...';

            fetch('/admin/api/issue-book', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({
                    book_id: currentScannedBook.id,
                    student_id: currentVerifiedStudent.student_id
                })
            })
            .then(parseJsonResponse)
            .then(data => {
                btnConfirmIssue.innerHTML = '<i class="bi bi-check-circle me-1"></i> Confirm Issue';
                if (data.success) {
                    showIssueAlert('success', data.message);
                    // Refresh book info cleanly
                    const bookIdToRefresh = currentScannedBook.id;
                    setTimeout(() => {
                        lookupBookByQR(`BOOK_ID:${bookIdToRefresh}`);
                    }, 1500);
                } else {
                    btnConfirmIssue.disabled = false;
                    showIssueAlert('danger', data.message || data.error || 'Failed to issue book.');
                }
            })
            .catch(err => {
                btnConfirmIssue.disabled = false;
                btnConfirmIssue.innerHTML = '<i class="bi bi-check-circle me-1"></i> Confirm Issue';
                showIssueAlert('danger', err.message || 'Server error while processing issue request.');
            });
        });
    }

    if (btnCancelIssue) {
        btnCancelIssue.addEventListener('click', function() {
            if (qrIssueSection) qrIssueSection.classList.add('d-none');
            resetIssueForm();
        });
    }

    if (btnCloseIssueSection) {
        btnCloseIssueSection.addEventListener('click', function() {
            if (qrIssueSection) qrIssueSection.classList.add('d-none');
            resetIssueForm();
        });
    }

    function showIssueAlert(type, text) {
        if (!qrIssueAlert) return;
        qrIssueAlert.className = `alert alert-${type} py-2 px-3 mb-3 small d-block`;
        qrIssueAlert.textContent = text;
    }
});


function playBeepSound() {
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(880, audioCtx.currentTime); // A5 note
        gain.gain.setValueAtTime(0.1, audioCtx.currentTime);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.15);
    } catch (e) {
        // AudioContext not allowed without interaction, ignore
    }
}

