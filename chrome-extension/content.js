// Quick Job Saver — Content Script
// Detects job information from the current page

(function() {
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'extractJob') {
      const job = extractJobFromPage();
      sendResponse({ job });
    }
    return true; // async response
  });

  function extractJobFromPage() {
    const job = {
      title: '',
      company: '',
      location: '',
      salary: '',
      description: '',
    };

    const url = window.location.href;
    const hostname = window.location.hostname;

    // Generic extraction strategies
    job.title = extractTitle();
    job.company = extractCompany();
    job.location = extractLocation();
    job.salary = extractSalary();

    return job;
  }

  function extractTitle() {
    // Try common selectors
    const selectors = [
      '[class*="job-title"]', '[class*="jobTitle"]', '[class*="position-title"]',
      'h1[class*="title"]', 'h1', '[data-test="job-title"]',
      '.job-header h1', '.posting-title h1', '[class*="role-title"]',
    ];

    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.textContent.trim().length > 3 && el.textContent.trim().length < 150) {
        return el.textContent.trim();
      }
    }

    // Try meta tags
    const ogTitle = document.querySelector('meta[property="og:title"]');
    if (ogTitle) return ogTitle.content;

    return document.title.split(' - ')[0].split(' | ')[0].trim();
  }

  function extractCompany() {
    const selectors = [
      '[class*="company-name"]', '[class*="companyName"]', '[class*="employer"]',
      '[data-test="company-name"]', '.company h2', '[class*="org-name"]',
      'a[class*="company"]', '[class*="hiring-org"]',
    ];

    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.textContent.trim().length > 1 && el.textContent.trim().length < 80) {
        return el.textContent.trim();
      }
    }

    // Try meta tags
    const ogSite = document.querySelector('meta[property="og:site_name"]');
    if (ogSite) return ogSite.content;

    return '';
  }

  function extractLocation() {
    const selectors = [
      '[class*="location"]', '[class*="job-location"]', '[class*="jobLocation"]',
      '[data-test="location"]', '[class*="city"]', '[class*="place"]',
    ];

    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.textContent.trim().length > 1 && el.textContent.trim().length < 100) {
        const text = el.textContent.trim();
        // Filter out noise
        if (text.match(/remote|hybrid|onsite|bangkok|thailand|singapore|tokyo|london|new york|san francisco|berlin/i)) {
          return text;
        }
      }
    }

    // Check page text for location patterns
    const bodyText = document.body.innerText.substring(0, 5000);
    const locationMatch = bodyText.match(/(remote|hybrid|onsite)[\s—–-]*(bangkok|thailand|singapore|tokyo|london|new york|san francisco|berlin|worldwide|global)?/i);
    if (locationMatch) return locationMatch[0];

    return '';
  }

  function extractSalary() {
    const selectors = [
      '[class*="salary"]', '[class*="compensation"]', '[class*="pay-range"]',
      '[data-test="salary"]', '[class*="comp"]',
    ];

    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) {
        const text = el.textContent.trim();
        if (text.match(/\$|฿|€|£|\d+[kK]|\d{3,}/)) {
          return text;
        }
      }
    }

    // Search page text for salary patterns
    const bodyText = document.body.innerText.substring(0, 10000);
    const salaryMatch = bodyText.match(/(\$[\d,]+[kK]?\s*[-–—to]+\s*\$[\d,]+[kK]?)/);
    if (salaryMatch) return salaryMatch[0];

    return '';
  }

  // Add floating save button to job pages
  function addFloatingButton() {
    const hostname = window.location.hostname;
    const jobPatterns = [
      /linkedin\.com\/jobs/,
      /indeed\.com\/viewjob/,
      /glassdoor\.com.*job-listing/,
      /remotive\.com\/jobs/,
      /weworkremotely\.com\/jobs/,
      /wellfound\.com\/jobs/,
      /otta\.com\/jobs/,
      /dice\.com\/jobs/,
      /jobthai\.com/,
    ];

    const isJobPage = jobPatterns.some(p => p.test(window.location.href));
    if (!isJobPage) return;

    const btn = document.createElement('button');
    btn.id = 'qjs-float-btn';
    btn.innerHTML = '💾 Save Job';
    btn.title = 'Save to Solo Empire Pipeline';
    document.body.appendChild(btn);

    btn.addEventListener('click', () => {
      const job = extractJobFromPage();
      chrome.runtime.sendMessage({
        action: 'quickSave',
        job: { ...job, url: window.location.href, board: hostname }
      });

      btn.innerHTML = '✅ Saved!';
      btn.style.background = '#22c55e';
      setTimeout(() => {
        btn.innerHTML = '💾 Save Job';
        btn.style.background = '#3b82f6';
      }, 2000);
    });
  }

  // Add button after page loads
  if (document.readyState === 'complete') {
    addFloatingButton();
  } else {
    window.addEventListener('load', addFloatingButton);
  }
})();
