// Quick Job Saver — Background Service Worker

// Create context menu on install
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'saveJob',
    title: '💼 Save job to Pipeline',
    contexts: ['page', 'link'],
  });

  chrome.contextMenus.create({
    id: 'saveAndApply',
    title: '📤 Save & mark as Applied',
    contexts: ['page', 'link'],
  });
});

// Handle context menu clicks
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === 'saveJob' || info.menuItemId === 'saveAndApply') {
    const url = info.linkUrl || tab.url;
    const jobData = {
      title: tab.title || 'Unknown Position',
      company: '',
      url: url,
      location: '',
      salary: '',
      notes: '',
      board: new URL(url).hostname.replace('www.', ''),
      saved_at: new Date().toISOString(),
      status: info.menuItemId === 'saveAndApply' ? 'applied' : 'saved',
    };

    // Save to storage
    const { savedJobs = [] } = await chrome.storage.local.get(['savedJobs']);
    savedJobs.push(jobData);
    await chrome.storage.local.set({ savedJobs });

    // Update stats
    const { stats = {} } = await chrome.storage.local.get(['stats']);
    stats.saved = (stats.saved || 0) + 1;
    stats.todaySaved = (stats.todaySaved || 0) + 1;
    stats.lastDate = new Date().toDateString();
    if (jobData.status === 'applied') stats.applied = (stats.applied || 0) + 1;
    await chrome.storage.local.set({ stats });

    // Notify user
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/icon128.png',
      title: 'Job Saved!',
      message: `${jobData.title} saved to pipeline.`,
    });
  }
});

// Handle messages from popup and content script
chrome.runtime.onMessage.addListener(async (request, sender, sendResponse) => {
  if (request.action === 'saveJob' || request.action === 'quickSave') {
    // Export to CSV periodically
    const { savedJobs = [] } = await chrome.storage.local.get(['savedJobs']);

    // Auto-export when 10+ jobs saved
    if (savedJobs.length >= 10) {
      await exportToCSV(savedJobs);
    }
  }
});

// Export saved jobs to CSV format compatible with pipeline
async function exportToCSV(jobs) {
  const header = 'id,title,company,url,location,salary_min,salary_max,board,source,scraped_at,description\n';
  const rows = jobs.map((job, i) => {
    const id = `chrome_${Date.now()}_${i}`;
    const title = escapeCsv(job.title);
    const company = escapeCsv(job.company);
    const url = escapeCsv(job.url);
    const location = escapeCsv(job.location);
    const board = escapeCsv(job.board);
    const savedAt = job.saved_at || new Date().toISOString();
    return `${id},${title},${company},${url},${location},0,0,${board},chrome_extension,${savedAt},`;
  }).join('\n');

  // Store CSV in chrome storage for later retrieval
  await chrome.storage.local.set({
    lastExport: {
      csv: header + rows,
      exportedAt: new Date().toISOString(),
      jobCount: jobs.length,
    }
  });
}

function escapeCsv(value) {
  if (!value) return '';
  const str = String(value);
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

// Keyboard shortcut: Ctrl+Shift+S to save current page as job
chrome.commands && chrome.commands.onCommand && chrome.commands.onCommand.addListener(async (command) => {
  if (command === 'save-job') {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const jobData = {
      title: tab.title || 'Unknown Position',
      url: tab.url,
      board: new URL(tab.url).hostname.replace('www.', ''),
      saved_at: new Date().toISOString(),
      status: 'saved',
    };

    const { savedJobs = [] } = await chrome.storage.local.get(['savedJobs']);
    savedJobs.push(jobData);
    await chrome.storage.local.set({ savedJobs });
  }
});
