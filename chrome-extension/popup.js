// Quick Job Saver — Popup Script
document.addEventListener('DOMContentLoaded', async () => {
  const saveBtn = document.getElementById('saveBtn');
  const saveApplyBtn = document.getElementById('saveApplyBtn');
  const successMsg = document.getElementById('successMsg');
  const jobStatus = document.getElementById('jobStatus');

  // Load saved counts
  const data = await chrome.storage.local.get(['savedJobs', 'stats']);
  const stats = data.stats || { saved: 0, applied: 0, todaySaved: 0, lastDate: '' };

  // Reset daily counter
  const today = new Date().toDateString();
  if (stats.lastDate !== today) {
    stats.todaySaved = 0;
    stats.lastDate = today;
  }

  document.getElementById('savedCount').textContent = stats.todaySaved || 0;
  document.getElementById('totalCount').textContent = stats.saved || 0;
  document.getElementById('appliedCount').textContent = stats.applied || 0;

  // Get current tab info and detect job data
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  // Try to extract job info from the page
  chrome.tabs.sendMessage(tab.id, { action: 'extractJob' }, (response) => {
    if (chrome.runtime.lastError) {
      // Content script not loaded — try to extract from URL
      extractFromUrl(tab.url);
      return;
    }
    if (response && response.job) {
      populateForm(response.job);
      jobStatus.classList.add('detected');
      jobStatus.innerHTML = `
        <p>✅ Job detected:</p>
        <div class="job-title">${response.job.title || 'Unknown'}</div>
        <div class="company">${response.job.company || 'Unknown'}</div>
      `;
    } else {
      extractFromUrl(tab.url);
    }
  });

  function extractFromUrl(url) {
    const urlObj = new URL(url);
    jobStatus.innerHTML = `<p>📋 Manual entry — fill in details below</p>`;

    // Try to extract from URL patterns
    const patterns = {
      'linkedin.com': /\/jobs\/view\/\d+/,
      'indeed.com': /\/viewjob\?jk=/,
      'glassdoor.com': /\/job-listing\//,
      'remotive.com': /\/jobs\//,
      'weworkremotely.com': /\/jobs\//,
      'wellfound.com': /\/jobs\//,
      'otta.com': /\/jobs\//,
    };

    for (const [domain, pattern] of Object.entries(patterns)) {
      if (url.includes(domain)) {
        jobStatus.innerHTML += `<p style="margin-top:4px;font-size:12px;color:#60a5fa">Detected: ${domain}</p>`;
        document.getElementById('location').value = 'Remote';
        break;
      }
    }
  }

  function populateForm(job) {
    if (job.title) document.getElementById('jobTitle').value = job.title;
    if (job.company) document.getElementById('company').value = job.company;
    if (job.location) document.getElementById('location').value = job.location;
    if (job.salary) document.getElementById('salary').value = job.salary;
  }

  async function saveJob(markApplied = false) {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    const jobData = {
      title: document.getElementById('jobTitle').value || 'Unknown Position',
      company: document.getElementById('company').value || 'Unknown',
      url: tab.url,
      location: document.getElementById('location').value || '',
      salary: document.getElementById('salary').value || '',
      notes: document.getElementById('notes').value || '',
      board: new URL(tab.url).hostname.replace('www.', ''),
      saved_at: new Date().toISOString(),
      status: markApplied ? 'applied' : 'saved',
    };

    // Save to chrome storage
    const { savedJobs = [] } = await chrome.storage.local.get(['savedJobs']);
    savedJobs.push(jobData);
    await chrome.storage.local.set({ savedJobs });

    // Update stats
    stats.saved = (stats.saved || 0) + 1;
    stats.todaySaved = (stats.todaySaved || 0) + 1;
    stats.lastDate = today;
    if (markApplied) stats.applied = (stats.applied || 0) + 1;
    await chrome.storage.local.set({ stats });

    // Update UI
    document.getElementById('savedCount').textContent = stats.todaySaved;
    document.getElementById('totalCount').textContent = stats.saved;
    document.getElementById('appliedCount').textContent = stats.applied;

    // Show success
    successMsg.style.display = 'block';
    successMsg.textContent = markApplied ? '✅ Saved & marked as applied!' : '✅ Job saved to pipeline!';

    // Send to background for CSV export
    chrome.runtime.sendMessage({ action: 'saveJob', job: jobData });

    // Reset form after delay
    setTimeout(() => {
      successMsg.style.display = 'none';
    }, 3000);
  }

  saveBtn.addEventListener('click', () => saveJob(false));
  saveApplyBtn.addEventListener('click', () => saveJob(true));
});
