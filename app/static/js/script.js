const appState = {
    currentSessionId: null,
    isGenerating: false,
    currentMode: 'txt2img', // Default generation mode (only mode now)
    
    // Getters
    getCurrentSession() {
        return this.currentSessionId;
    },
    async ensureSession() {
      const savedSessionId = localStorage.getItem('currentSessionId');
      if (savedSessionId) {
          try {
              const response = await fetchWithRetry(`/chat/session/${savedSessionId}`);
              if (response.ok) {
                  this.currentSessionId = savedSessionId;
                  return savedSessionId;
              } else {
                  // Don't auto-create here
                  throw new Error('Invalid session');
              }
          } catch (error) {
              console.error("Error verifying saved session:", error);
              // Don't create a new chat here
          }
      }
      return null; // Let the caller decide if it wants to create a new chat
  },
    getCurrentMode() {
        return this.currentMode;
    },
    
    // Setters with validation
    setCurrentSession(sessionId) {
        this.currentSessionId = sessionId;
        // Save to localStorage for persistence across page refreshes
        localStorage.setItem('currentSessionId', sessionId);
    },
    
    setGenerating(status) {
        this.isGenerating = Boolean(status);
    }
};

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeApp);
} else {
  initializeApp();
}

function getCSRFToken() {
  return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
}

async function initializeApp() {
  const chatInput = document.getElementById('chat-input');
  const styleSelector = document.getElementById('style-selector');
  const chatForm = document.getElementById('chat-form');
  if (chatInput) {
    chatInput.addEventListener('input', function () {
      this.style.height = 'auto';
      this.style.height = this.scrollHeight + 'px';
    });
  }
  const savedSessionId = localStorage.getItem('currentSessionId');
  let mostRecentSessionId = await updateChatList(); 

  try {
    if (savedSessionId) {
      const response = await fetchWithRetry(`/chat/session/${savedSessionId}`);
      if (response.ok) {
        appState.setCurrentSession(savedSessionId);
        await loadChat(savedSessionId);
      } else {
        console.warn('⚠️ Saved session not valid, trying most recent session...');
        localStorage.removeItem('currentSessionId');
        if (mostRecentSessionId) {
          appState.setCurrentSession(mostRecentSessionId);
          await loadChat(mostRecentSessionId);
        } else {
          await createNewChat();
        }
      }
    } else if (mostRecentSessionId) {
      appState.setCurrentSession(mostRecentSessionId);
      await loadChat(mostRecentSessionId);
    } else {
      await createNewChat();
    }
  } catch (err) {
    console.error('❌ Error during initialization:', err);
    await createNewChat();
  }

  
  document.getElementById('new-design-btn')?.addEventListener('click', async () => {
    const sessionId = await createNewChat();
    console.log('✅ Created new session:', sessionId);
  });

  if (chatForm) {
    chatForm.removeEventListener('submit', handleSendMessage);  // Remove any old listener
    chatForm.addEventListener('submit', function (e) {
      e.preventDefault();
      handleSendMessage();
    });
  }
  if (!appState.getCurrentSession()) {
    console.warn("⚠️ No session active after init — forcing new session.");
    await createNewChat();
  }
}

function shortUrl(url, maxLength = 40) {
  if (!url) return '';
  return url.length > maxLength ? url.substring(0, maxLength - 3) + '...' : url;
}
/**
 * Toggles the sidebar visibility on both mobile and desktop.
 * Adjusts main content margins accordingly.
 */
window.toggleSidebar = function () {

    const sidebar = document.getElementById('sidebar');
    const mainContent = document.querySelector('main');
  
    sidebar.classList.toggle('hidden');
  
    if (!sidebar.classList.contains('hidden')) {
      sidebar.classList.add('block');
      mainContent.classList.add('md:ml-64');
      mainContent.classList.remove('ml-0');
    } else {
      sidebar.classList.remove('block');
      mainContent.classList.remove('md:ml-64');
      mainContent.classList.add('ml-0');
    }
  }
/**
 * Creates a new chat session via API.
 * Updates the current session ID and loads the new chat.
 * Clears the chat messages and shows a welcome message.
 * Updates chat list sidebar.
 * 
 * @returns {Promise<string|null>} - New session ID or null on failure
 */
async function createNewChat() {
  try {
    const response = await fetchWithRetry('/chat/new', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCSRFToken()  
      },
      body: JSON.stringify({ name: `Chat ${new Date().toLocaleString()}` })
    });

    if (!response.ok) throw new Error('Failed to create new chat');

    const data = await response.json();
    const sessionId = data.session_id;

    appState.setCurrentSession(sessionId);

    // Clear chat UI and insert welcome message
    const chatContainer = document.getElementById('chat-messages');
    if (chatContainer) {
      chatContainer.innerHTML = '';
      chatContainer.scrollTop = 0;

      const welcomeDiv = document.createElement('div');
      welcomeDiv.className = 'bot-message mb-3 mt-4';
      welcomeDiv.innerHTML = `
        <h2 class="font-semibold text-base mb-1">Welcome to Living Room Style Analyzer</h2>
        <p class="text-sm">Describe your dream living room, and I'll help you analyze its style and generate design ideas!</p>
        <p class="text-sm mt-2">Simply type your description below and I'll create an AI-generated image of your living room design.</p>
      `;
      chatContainer.appendChild(welcomeDiv);
    }

    await updateChatList();
    await loadChat(sessionId);
    showSuccess('New design chat created');
    console.log('[createNewChat] New session ID:', sessionId);
    return sessionId;
  } catch (error) {
    showError('Failed to create new chat: ' + error.message);
    console.error('Error creating new chat:', error);
    return null;
  }
}


/**
 * Fetches chat sessions and updates the sidebar chat list.
 * Adds event listeners for chat selection, renaming, and deletion.
 * 
 * @returns {Promise<string|null>} The most recent session ID or null if none
 */
async function updateChatList() {
    try {
      const response = await fetchWithRetry('/chat/sessions');
      if (!response.ok) {
        throw new Error('Failed to fetch chat sessions');
      }
  
      const sessions = await response.json();
      const chatList = document.querySelector('.chat-list');
      let mostRecentSessionId = null;
  
      if (chatList) {
        if (sessions.length === 0) {
          chatList.innerHTML = '<div class="text-gray-500 text-xs p-2">No recent designs</div>';
          return null;
        }
  
        chatList.innerHTML = '';
  
        sessions.forEach((session, index) => {
          if (index === 0) {
            mostRecentSessionId = session.session_id; // first session is most recent
          }
  
          const chatItem = document.createElement('div');
          chatItem.className = `chat-item flex items-center justify-between p-1.5 rounded hover:bg-gray-100 cursor-pointer ${session.session_id === appState.getCurrentSession() ? 'active' : ''}`;
          chatItem.dataset.uuid = session.session_id;
  
          chatItem.innerHTML = `
            <div class="chat-item-content flex items-center gap-2 flex-1 overflow-hidden">
              <i class="fas fa-comment-alt text-gray-600"></i>
              <span class="truncate">${session.name}</span>
            </div>
            <div class="chat-item-actions flex">
              <button class="rename-chat-btn text-gray-500 hover:text-blue-500 px-1" title="Rename">
                <i class="fas fa-edit text-xs"></i>
              </button>
              <button class="delete-chat-btn text-gray-500 hover:text-red-500 px-1" title="Delete">
                <i class="fas fa-trash text-xs"></i>
              </button>
            </div>
          `;
  
          // Load chat when chat item clicked (excluding buttons)
          chatItem.addEventListener('click', function (e) {
            if (!e.target.closest('.rename-chat-btn') && !e.target.closest('.delete-chat-btn')) {
              loadChat(session.session_id);
            }
          });
  
          // Rename chat button
          chatItem.querySelector('.rename-chat-btn').addEventListener('click', function () {
            renameChat(this);
          });
  
          // Delete chat button
          chatItem.querySelector('.delete-chat-btn').addEventListener('click', function () {
            deleteChat(this);
          });
  
          chatList.appendChild(chatItem);
        });
      }
  
      return mostRecentSessionId;
    } catch (error) {
      console.error('Error updating chat list:', error);
      return null;
    }
  }

async function loadChat(sessionId) {
  try {
    appState.setCurrentSession(sessionId);

    // Highlight selected chat item in sidebar
    document.querySelectorAll('.chat-item').forEach(item => {
      item.classList.toggle('active', item.dataset.uuid === sessionId);
    });

    // Fetch user ratings before loading messages
    let userRatings = {};
    try {
      const ratingsResponse = await fetch('/api/ratings');
      if (ratingsResponse.ok) {
        const ratingsData = await ratingsResponse.json();
        if (ratingsData.success && ratingsData.ratings) {
          ratingsData.ratings.forEach(r => {
            userRatings[r.image_url] = r;
          });
        }
      } else {
        console.warn('Failed to fetch ratings');
      }
    } catch (error) {
      console.error('Error fetching ratings:', error);
    }

    // Fetch chat messages
    const response = await fetchWithRetry(`/chat/session/${sessionId}`);
    if (!response.ok) {
      showError('Unable to load chat history. Try refreshing or start a new chat.');
      throw new Error('Failed to load chat history');
    }

    const data = await response.json();
    const messages = data.messages || [];
    const chatContainer = document.getElementById('chat-messages');

    if (chatContainer) {
      chatContainer.innerHTML = '';

  if (messages.length === 0) {
    const welcomeDiv = document.createElement('div');
    welcomeDiv.className = 'bot-message mb-3 mt-4';

    // This block might be using conditions, but we want to remove that and hardcode the long message
    welcomeDiv.innerHTML = `
      <h2 class="font-semibold text-base mb-1">Welcome to Living Room Style Analyzer</h2>
      <p class="text-sm">Describe your dream living room, and I'll help you analyze its style and generate design ideas!</p>
      <p class="text-sm mt-2">Simply type your description below and I'll create an AI-generated image of your living room design.</p>
    `;

    chatContainer.appendChild(welcomeDiv);
  }
 else {
        messages.forEach(msg => {
          const role = msg.is_user ? 'user' : 'assistant';
          const styleInfo = (!msg.is_user && msg.image_url && msg.style_data) ? {
            detected_style: msg.style_data.detected_style,
            style_reasons: msg.style_data.style_reasons
          } : null;

          const ratingData = (msg.image_url && userRatings[msg.image_url]) ? userRatings[msg.image_url] : null;

          appendMessage(role, msg.content, msg.image_url, styleInfo, ratingData, msg.id);
        });
      }

      scrollToMessageIfNeeded();
      await initializeFavoriteButtons();
      setupRatingSystem();
    }

    const chatForm = document.getElementById('chat-form');
    if (chatForm) {
      chatForm.dataset.sessionId = sessionId;
    }

    // Reset the flag once loaded
    appState.isNewSession = false;

  } catch (error) {
    console.error('Error loading chat:', error);
    showError('Failed to load chat history: ' + error.message);
  }
}


/**
 * Handles sending the user chat message.
 * - Validates input
 * - Ensures session
 * - Sends message and style to backend
 * - Processes and displays response including images, style explanation, favorites, and rating UI.
 */
async function handleSendMessage() {
  const chatInput = document.getElementById('chat-input');
  const styleSelector = document.getElementById('style-selector');
  if (!chatInput) return;

  const message = chatInput.value.trim();
  if (!message || appState.isGenerating) return;

  const validation = validateUserInput(message);
  if (!validation.valid) {
    showError(validation.message);
    return;
  }

  const style = styleSelector ? styleSelector.value : '';
  const sessionId = await appState.ensureSession();
  if (!sessionId) {
    showError("No valid chat session. Please start a new design.");
    return;
  }

  try {
    chatInput.value = '';
    chatInput.style.height = 'auto';
    showLoading('Generating your design...');
    appState.setGenerating(true);

    function getCSRFToken() {
      return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    }

    
    appendMessage('user', message);
    const response = await fetch('/api/generate-image', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCSRFToken()
      },
      body: JSON.stringify({
        prompt: message,
        style: style,
        session_id: sessionId
      })
    });

    if (!response.ok) {
      const errorData = await response.json();
        if (response.status === 400 && errorData.assistant_message) {
        appendMessage('assistant', errorData.assistant_message.content);
        showError(errorData.assistant_message.content);  // optional toast/banner
        return;
      }
    
      throw new Error(errorData.message || 'Image generation failed');
    }
    
    const data = await response.json();

    if (!data || !data.image || typeof data.message !== 'string') {
      throw new Error('Invalid response from server. Missing image or message.');
    }

    const imageUrl = data.image.startsWith('data:image')
      ? data.image
      : 'data:image/png;base64,' + data.image;
    
    console.log('Generated image URL:', shortUrl(imageUrl));
    appendMessage('assistant', data.message, imageUrl, data.style_data || null, null);
    showRating();
    setupRatingSystem();

    setTimeout(() => {
      const chatContainer = document.getElementById('chat-messages');
      if (chatContainer) {
        chatContainer.scrollTop = chatContainer.scrollHeight;
      }
    }, 100);
    console.log('[handleSendMessage] Current session ID:', sessionId);

  } catch (error) {
    console.error('❌ Error in handleSendMessage:', error);
    appendMessage('assistant', `Sorry, there was a problem: ${error.message}`);
    showError(safeErrorMessage(error.message));

  } finally {
    appState.setGenerating(false);
    hideLoading();
  }
}

/**
 * Shows a loading overlay with an optional message.
 * Creates the overlay if it doesn't exist.
 * 
 * @param {string} message - Loading message to display (default: 'Loading...')
 */
function showLoading(message = 'Loading...') {
    let loadingOverlay = document.getElementById('loading-overlay');
    let loadingMessage = document.getElementById('loading-message');

    if (!loadingOverlay) {
        loadingOverlay = document.createElement('div');
        loadingOverlay.id = 'loading-overlay';
        loadingOverlay.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); display: flex; justify-content: center; align-items: center; z-index: 9999;';

        const spinner = document.createElement('div');
        spinner.className = 'loading-spinner';
        spinner.style.cssText = 'border: 5px solid #f3f3f3; border-top: 5px solid #3498db; border-radius: 50%; width: 50px; height: 50px; animation: spin 2s linear infinite;';

        loadingMessage = document.createElement('div');
        loadingMessage.id = 'loading-message';
        loadingMessage.style.cssText = 'color: white; margin-left: 15px; font-size: 18px;';
        loadingMessage.textContent = message;

        const container = document.createElement('div');
        container.style.cssText = 'display: flex; align-items: center;';
        container.appendChild(spinner);
        container.appendChild(loadingMessage);

        loadingOverlay.appendChild(container);
        document.body.appendChild(loadingOverlay);

        // Add spinner animation CSS
        const style = document.createElement('style');
        style.textContent = '@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }';
        document.head.appendChild(style);
    } else {
        loadingOverlay.style.display = 'flex';
        if (loadingMessage) {
            loadingMessage.textContent = message;
        }
    }
}

/**
 * Hides the loading overlay if it exists.
 */
function hideLoading() {
    const loadingOverlay = document.getElementById('loading-overlay');
    if (loadingOverlay) {
        loadingOverlay.style.display = 'none';
    }
}
/**
 * Sets up click event listeners on all download buttons.
 * Each button downloads the corresponding image in the chosen format.
 */
function setupDownloadButtons() {
  document.querySelectorAll('.download-button').forEach(button => {
    button.removeEventListener('click', handleDownloadClick);
    button.addEventListener('click', handleDownloadClick);
  });
}

function handleDownloadClick(event) {
  event.preventDefault();
  const button = event.currentTarget;
  const imageUrl = button.dataset.imageUrl;
  if (!imageUrl) {
    showError('Image URL not found for download.');
    return;
  }
  const link = document.createElement('a');
  link.href = imageUrl;
  link.download = 'living-room-design.png';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
/**
 * Shows a success flash message.
 * Automatically dismisses after 5 seconds.
 * 
 * @param {string} message - The success message to show.
 */
function showSuccess(message) {
    const flashContainer = document.getElementById('flash-messages');
    if (!flashContainer) return;
  
    const flashDiv = document.createElement('div');
    flashDiv.className = 'bg-white p-4 rounded-lg shadow-md mb-4 flex justify-between items-center';
    flashDiv.innerHTML = `
      <div class="flex items-center">
        <i class="fas fa-check-circle text-green-500 mr-2"></i>
        <span>${escapeHTML(message)}</span>
      </div>
      <button class="close-flash text-gray-500 hover:text-gray-700" title="Close">
        <i class="fas fa-times"></i>
      </button>
    `;
  
    flashContainer.appendChild(flashDiv);
  
    // Close button click handler
    flashDiv.querySelector('.close-flash').addEventListener('click', () => {
      flashDiv.remove();
    });
  
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
      if (flashDiv.parentNode) {
        flashDiv.remove();
      }
    }, 5000);
  }
/**
 * Shows an error flash message.
 * Automatically dismisses after 5 seconds.
 * 
 * @param {string} message - The error message to show.
 */
function showError(message) {
    const flashContainer = document.getElementById('flash-messages');
    if (!flashContainer) return;
  
    const flashDiv = document.createElement('div');
    flashDiv.className = 'bg-white p-4 rounded-lg shadow-md mb-4 flex justify-between items-center';
    flashDiv.innerHTML = `
      <div class="flex items-center">
        <i class="fas fa-exclamation-circle text-red-500 mr-2"></i>
        <span>${escapeHTML(message)}</span>
      </div>
      <button class="close-flash text-gray-500 hover:text-gray-700" title="Close">
        <i class="fas fa-times"></i>
      </button>
    `;
  
    flashContainer.appendChild(flashDiv);
  
    // Close button click handler
    flashDiv.querySelector('.close-flash').addEventListener('click', () => {
      flashDiv.remove();
    });
  
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
      if (flashDiv.parentNode) {
        flashDiv.remove();
      }
    }, 5000);
  }

/**
 * Prompts the user to rename a chat session.
 * Sends the rename request to backend and updates the UI accordingly.
 * 
 * @param {HTMLElement} button - The rename button element clicked
 */
async function renameChat(button) {
  try {
    const chatItem = button.closest('.chat-item');
    if (!chatItem) return;

    const sessionId = chatItem.dataset.uuid;
    const nameElement = chatItem.querySelector('.truncate');
    if (!sessionId || !nameElement) return;

    const currentName = nameElement.textContent || '';
    const rawNew = prompt('Enter a new name for this chat:', currentName);
    if (rawNew == null) return; // user cancelled

    const newName = rawNew.trim();

    // Basic client-side validation
    if (!newName) {
      showError('Name cannot be empty.');
      return;
    }
    if (newName.length > 120) {
      showError('Name is too long (max 120 characters).');
      return;
    }
    if (newName === currentName) {
      return; // no change
    }

    const res = await fetch('/chat/rename', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCSRFToken()
      },
      body: JSON.stringify({ session_id: sessionId, name: newName })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || err.message || 'Failed to rename chat');
    }

    // Safe DOM update (textContent, not innerHTML)
    nameElement.textContent = newName;

    showSuccess('Chat renamed successfully');
    await updateChatList(); // refresh sidebar state
  } catch (error) {
    console.error('Error renaming chat:', error);
    showError('Failed to rename chat');
  }
}

/**
 * Deletes a chat session after user confirmation.
 * Removes the chat item from the list,
 * creates a new chat if the deleted chat was the current session,
 * and shows success or error messages.
 * 
 * @param {HTMLElement} button - The delete button element clicked
 */
async function deleteChat(button) {
  if (!confirm('Are you sure you want to delete this chat? This action cannot be undone.')) {
    return;
  }

  const chatItem = button.closest('.chat-item');
  const sessionId = chatItem.dataset.uuid;

  try {
    const response = await fetch('/chat/delete', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCSRFToken()  
      },
      body: JSON.stringify({ session_id: sessionId })   
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(data.message || 'Failed to delete chat');
    }

    chatItem.remove();
    if (sessionId === appState.getCurrentSession()) {
      const remainingItems = document.querySelectorAll('.chat-item');
      if (remainingItems.length > 0) {
        const nextSessionId = remainingItems[0].dataset.uuid;
        await loadChat(nextSessionId);
        appState.setCurrentSession(nextSessionId);
      } else {
        const newSessionId = await createNewChat();
        appState.setCurrentSession(newSessionId);
      }
    }

    showSuccess(data.message || 'Chat deleted successfully');
  } catch (error) {
    // Log minimal info to console (optional)
    console.warn('Delete chat failed:', error.message);
    // Show safe message to user
    showError('Could not delete chat. Please try again.');
  }
}


// Add this function to show a warning banner
function showBackendWarning(message) {
    // Create warning banner if it doesn't exist
    if (!document.getElementById('backend-warning')) {
        const warningBanner = document.createElement('div');
        warningBanner.id = 'backend-warning';
        warningBanner.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; background-color: #f8d7da; color: #721c24; padding: 10px; text-align: center; z-index: 10000; font-weight: bold;';
        warningBanner.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="margin-right: 10px;">⚠️</span>
                <span style="flex-grow: 1;">${message}</span>
                <button onclick="this.parentElement.parentElement.style.display='none';" style="background: none; border: none; cursor: pointer; font-weight: bold;">✕</button>
            </div>
        `;
        document.body.prepend(warningBanner);
    }
}

/**
 * Performs a fetch request with retry on failure and timeout support.
 * Retries up to maxRetries times with exponential backoff.
 *
 * @param {string} url - The request URL
 * @param {object} options - Fetch options
 * @param {number} maxRetries - Maximum retry attempts (default 2)
 * @param {number} timeout - Timeout in ms (default 30000)
 * @returns {Promise<Response>} The fetch response
 */
async function fetchWithRetry(url, options = {}, maxRetries = 2, timeout = 30000) {
    let retries = 0;
  
    while (retries <= maxRetries) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);
  
        const response = await fetch(url, {
          ...options,
          signal: controller.signal
        });
  
        clearTimeout(timeoutId);
        return response;
      } catch (error) {
        retries++;
  
        console.info(`Retrying request to ${url} (${retries}/${maxRetries})`);
  
        if (error.name === 'AbortError') {
          console.warn(`Request timed out, retry ${retries}/${maxRetries}`);
        } else {
          console.error(`Fetch error, retry ${retries}/${maxRetries}:`, error);
        }
  
        if (retries > maxRetries) {
          throw error;
        }
  
        // Wait with exponential backoff before retrying
        await new Promise(resolve => setTimeout(resolve, 1000 * Math.pow(2, retries)));
      }
    }
  }
/**
 * Validates the user input message.
 * Ensures it is not empty and within acceptable length limits.
 *
 * @param {string} input - The user input string
 * @returns {object} Validation result with `valid` (boolean) and `message` (string)
 */
function validateUserInput(input) {
    if (!input || typeof input !== 'string') {
      return { valid: false, message: 'Input cannot be empty' };
    }
  
    const trimmed = input.trim();
    if (trimmed.length === 0) {
      return { valid: false, message: 'Input cannot be empty' };
    }
  
    if (trimmed.length < 3) {
      return { valid: false, message: 'Message is too short' };
    }
  
    if (trimmed.length > 500) {
      return { valid: false, message: 'Input is too long (maximum 500 characters)' };
    }
  
    return { valid: true };
  }

// Fetch user's current favorites from backend and return map image_url => favorite_id
async function fetchUserFavorites() {
  try {
    const response = await fetch('/api/favorites');
    if (!response.ok) throw new Error('Failed to fetch favorites');
    const data = await response.json();
    const favMap = {};
    if (data.favorites) {
      data.favorites.forEach(fav => {
        favMap[fav.image_url] = fav.id;
      });
    }
    return favMap;
  } catch (error) {
    console.error('Error fetching favorites:', error);
    return {};
  }
}

// Initialize favorite buttons: mark favorited ones and setup click handlers
async function initializeFavoriteButtons() {
  const favoritesMap = await fetchUserFavorites(); // image_url => favorite_id map

  document.querySelectorAll('.favorite-button').forEach(button => {
    const imageUrl = button.dataset.image;
    if (favoritesMap[imageUrl]) {
      button.dataset.favoriteId = favoritesMap[imageUrl];
      button.classList.remove('bg-yellow-500', 'hover:bg-yellow-600');
      button.classList.add('bg-green-500');
      button.innerHTML = '<i class="fas fa-check"></i> Added to Favorites';
    } else {
      button.classList.add('bg-yellow-500', 'hover:bg-yellow-600');
      button.innerHTML = '<i class="fas fa-star"></i> Favorite';
      delete button.dataset.favoriteId;
    }
  });
}

// Toggle favorite/unfavorite on button click
async function toggleFavorite(button) {
  const imageUrl = button.dataset.image;
  const prompt = button.dataset.prompt || '';
  const styleName = button.dataset.styleName || 'unknown';
  const favoriteId = button.dataset.favoriteId;
  const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

  button.disabled = true;

  try {
    if (favoriteId) {
      // Unfavorite
      const response = await fetch(`/api/favorites/${favoriteId}`, {
        method: 'DELETE',
        headers: {
          'X-CSRFToken': csrfToken
        },
        credentials: 'include'
      });

      const result = await response.json();
      if (!response.ok) throw new Error(result.message || 'Failed to remove favorite');

      delete button.dataset.favoriteId;
      button.classList.remove('bg-green-500');
      button.classList.add('bg-yellow-500', 'hover:bg-yellow-600');
      button.innerHTML = '<i class="fas fa-star"></i> Favorite';
      showSuccess(result.message || 'Removed from favorites');

    } else {
      // Add to favorites
      const response = await fetch('/api/favorite', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken
        },
        credentials: 'include',
        body: JSON.stringify({ image_url: imageUrl, prompt, style_name: styleName })
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.message || 'Failed to add favorite');

      if (data.favorite_id) {
        button.dataset.favoriteId = data.favorite_id;
        button.classList.remove('bg-yellow-500', 'hover:bg-yellow-600');
        button.classList.add('bg-green-500');
        button.innerHTML = '<i class="fas fa-check"></i> Favorited';
      }

      showSuccess(data.message || 'Image added to favorites');
    }
  } catch (err) {
    showError(err.message || 'Something went wrong');
  } finally {
    button.disabled = false;
  }
}

/**
 * Initializes rating stars and submit buttons.
 * Ensures only one event listener per element and handles user rating submission.
 */
function setupRatingSystem() {
  // Submit rating buttons
  setupStarClickListeners();
  document.querySelectorAll('.submit-rating').forEach(button => {
    addEventListenerOnce(button, 'click', async function () {
      const imageUrl = this.dataset.image;
      if (!imageUrl) {
        showError('Missing image URL for rating submission.');
        return;
      }

      const ratingContainer = this.closest('.rating-container');
      if (!ratingContainer) {
        showError('Rating container not found.');
        return;
      }

      // Extract ratings from datasets
      const relevance = parseInt(ratingContainer.querySelector('.star-rating[data-category="relevance"]').dataset.relevanceRating || 0);
      const quality = parseInt(ratingContainer.querySelector('.star-rating[data-category="quality"]').dataset.qualityRating || 0);
      const style = parseInt(ratingContainer.querySelector('.star-rating[data-category="style"]').dataset.styleRating || 0);

      if (!relevance || !quality || !style) {
        showError('Please provide ratings for all categories.');
        return;
      }

      let styleTag = 'Unknown';
      const botMessage = ratingContainer.closest('.bot-message');
      if (botMessage) {
        const detectedStyleEl = botMessage.querySelector('.style-explanation strong');
        if (detectedStyleEl) {
          styleTag = detectedStyleEl.textContent.trim();
        }
      }

      try {
        const response = await fetchWithRetry('/api/rate-image', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
          },
          body: JSON.stringify({
            image_url: imageUrl,
            prompt_relevance: relevance,
            image_quality: quality,
            style_accuracy: style,
            style_tag: styleTag  
          })
        });

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.message || 'Failed to submit rating');
        }

        
        this.disabled = true;
        this.textContent = 'Rating Submitted';
        this.classList.add('submitted');
        this.classList.remove('bg-purple-500', 'hover:bg-purple-600');
        this.classList.add('bg-gray-500', 'cursor-not-allowed', 'opacity-70');

      } catch (error) {
        console.error('Error submitting rating:', error);
        showError(`Failed to submit rating: ${error.message}`);
      }
    });

    button.dataset.listenerAttached = 'true';
  });
}

  function showRating() {
    const ratingContainer = document.querySelector('.rating-container');
    if (ratingContainer) {
      ratingContainer.style.display = 'block'; // or 'flex'
    }
  }

/**
 * Appends a chat message to the chat container.
 * Handles user and bot messages with optional images, favorites, ratings, and style explanation.
 * 
 * @param {string} sender - 'user' or 'assistant'
 * @param {string} text - The text content of the message
 * @param {string|null} imageUrl - Optional image URL if the message includes an image
 * @param {Object|null} styleInfo - Optional style information {detected_style, style_reasons}
 * @param {Object|null} ratingData - Optional rating info {prompt_relevance, image_quality, style_accuracy}
 */
function appendMessage(sender, text, imageUrl = null, styleInfo = null, ratingData = null, messageId = null) {
  const chatContainer = document.getElementById('chat-messages');
  if (!chatContainer) {
    console.error('Chat messages container not found');
    return;
  }

  const messageDiv = document.createElement('div');

  // ✅ Assign unique message ID for scroll targeting
  if (messageId) {
    messageDiv.id = `msg-${messageId}`;
  }

  messageDiv.className = sender === 'user' ? 'user-message' : 'bot-message';
  // Format message text
  const formattedText = escapeHTML(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>');

  let content = `<p>${formattedText}</p>`;

  // Helper to generate star icons with pre-filled active stars
  function generateStarRatingWithValue(category, rating = 0) {
    let html = `<span class="mr-2 text-sm font-medium text-gray-600">`;
    if (category === 'relevance') html += 'Prompt Relevance:';
    else if (category === 'quality') html += 'Image Quality:';
    else if (category === 'style') html += 'Style Accuracy:';
    html += `</span>`;

    for (let i = 1; i <= 5; i++) {
      const activeClass = i <= rating ? 'fas text-yellow-500' : 'far';
      html += `<i class="${activeClass} fa-star star-icon cursor-pointer" data-rating="${i}" data-category="${category}"></i>`;
    }
    return html;
  }

  // Add image if present
  if (imageUrl) {
    console.log('Submitting rating for image:', shortUrl(imageUrl));

    // Get existing ratings or default 0
    const relevanceRating = ratingData?.prompt_relevance || 0;
    const qualityRating = ratingData?.image_quality || 0;
    const styleRating = ratingData?.style_accuracy || 0;

    // Determine if rating already submitted
    const isSubmitted = relevanceRating > 0 && qualityRating > 0 && styleRating > 0;

    content += `
      <div class="mt-2 image-container">
        <img src="${imageUrl}" alt="Generated design" class="rounded-lg max-w-full h-auto generated-image" />
        <div class="image-actions mt-2 flex gap-2">
          <a href="${imageUrl}" download="generated_image.png"
             class="download-button bg-blue-500 text-white px-3 py-1 rounded text-sm hover:bg-blue-600" data-format="png">
            Download
          </a>
          <button class="favorite-button bg-yellow-500 text-white px-3 py-1 rounded text-sm hover:bg-yellow-600"
                  data-image="${imageUrl}" data-prompt="${escapeHTML(text)}">
            Add to Favorites
          </button>
        </div>
      </div>
      <div class="rating-container mt-3 p-3 bg-gray-50 rounded-lg shadow-sm max-w-md" style="display: block;">
        <h4 class="font-semibold mb-2 text-gray-700">Rate this image</h4>
        <div class="star-rating flex items-center mb-2" data-category="relevance" data-relevance-rating="${relevanceRating}">
          ${generateStarRatingWithValue('relevance', relevanceRating)}
        </div>
        <div class="star-rating flex items-center mb-2" data-category="quality" data-quality-rating="${qualityRating}">
          ${generateStarRatingWithValue('quality', qualityRating)}
        </div>
        <div class="star-rating flex items-center mb-4" data-category="style" data-style-rating="${styleRating}">
          ${generateStarRatingWithValue('style', styleRating)}
        </div>
        <button
          class="submit-rating bg-purple-500 hover:bg-purple-600 text-white py-1.5 px-4 rounded text-sm font-semibold transition"
          data-image="${imageUrl}"
          ${isSubmitted ? 'disabled style="cursor:not-allowed; opacity:0.7;"' : ''}
        >
          ${isSubmitted ? 'Rating Submitted' : 'Submit Rating'}
        </button>
      </div>
    `;
  }

  // Optional style explanation block
  if (styleInfo && styleInfo.detected_style) {
    content += `
      <div class="style-explanation mt-2">
        <strong>Detected Style:</strong> ${escapeHTML(styleInfo.detected_style)}<br>
        ${styleInfo.style_reasons?.map(reason => `• ${escapeHTML(reason)}`).join('<br>')}
      </div>`;
  }

  content += `<div class="message-time">${new Date().toLocaleTimeString()}</div>`;
  messageDiv.innerHTML = content;
  if (ratingData) {
    setTimeout(() => {
      setupRatingSystem(); // Apply visual star states
    }, 10);
  }
  
  chatContainer.appendChild(messageDiv);
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

/**
 * Escapes HTML to prevent XSS in chat content.
 */
function escapeHTML(str) {
  return str.replace(/[&<>'"]/g, tag => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[tag]));
}

/**
 * Shows a modal dialog to allow the user to override the detected style.
 * 
 * @param {string} imageUrl - URL of the image to provide feedback for
 * @param {string} originalStyle - The original detected style
 */
function showStyleOverrideModal(imageUrl, originalStyle) {
    // Create modal container
    const modalDiv = document.createElement('div');
    modalDiv.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
    modalDiv.id = 'style-override-modal';
  
    // Common style options
    const commonStyles = [
      'Modern', 'Contemporary', 'Minimalist', 'Scandinavian', 'Industrial',
      'Mid-Century Modern', 'Bohemian', 'Rustic', 'Traditional', 'Transitional',
      'Art Deco', 'Coastal', 'Farmhouse', 'Mediterranean', 'Japanese'
    ];
  
    // Build options HTML
    const styleOptions = commonStyles.map(style =>
      `<option value="${style}" ${style === originalStyle ? 'selected' : ''}>${style}</option>`
    ).join('');
  
    modalDiv.innerHTML = `
      <div class="bg-white p-4 rounded-lg max-w-lg w-full mx-4">
        <h3 class="text-lg font-bold mb-2">Suggest Different Style</h3>
        <div class="mb-3">
          <p class="text-sm">Original detected style: <strong>${originalStyle}</strong></p>
          <p class="text-sm mt-2">If you think this image represents a different style, please select it below:</p>
          <select id="corrected-style" class="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 rounded-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm">
            ${styleOptions}
          </select>
        </div>
        <div class="flex justify-end gap-2">
          <button id="cancel-override" class="px-3 py-1 bg-gray-300 rounded">Cancel</button>
          <button id="submit-override" class="px-3 py-1 bg-blue-500 text-white rounded">Submit</button>
        </div>
      </div>
    `;
  
    document.body.appendChild(modalDiv);
  
    // Event listeners
    document.getElementById('cancel-override').addEventListener('click', () => {
      modalDiv.remove();
    });
  
    document.getElementById('submit-override').addEventListener('click', async () => {
      const correctedStyle = document.getElementById('corrected-style').value;
  
      try {
        const response = await fetchWithRetry('/api/style-feedback', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()  
          },
          body: JSON.stringify({
            image_url: imageUrl,
            original_style: originalStyle,
            corrected_style: correctedStyle
          })
        });
  
        const data = await response.json();
  
        if (data.success) {
          showSuccess('Thank you for your feedback!');
          const botMessage = document.querySelector(`.bot-message img[src="${imageUrl}"]`)?.closest('.bot-message');
          if (botMessage) {
            const styleReason = botMessage.querySelector('.style-reason');
            if (styleReason) {
              styleReason.innerHTML = styleReason.innerHTML.replace(originalStyle, `${correctedStyle} (updated)`);
            }
          }
        } else {
          throw new Error(data.message || 'Failed to submit style feedback');
        }
      } catch (error) {
        console.error('Error submitting style feedback:', error);
        showError(`Failed to submit style feedback: ${error.message}`);
      } finally {
        modalDiv.remove();
      }
    });
  }
  
/**
 * Loads the user's favorite designs and renders them in the profile favorites tab.
 */
export async function loadFavorites() {
  const favoritesContainer = document.getElementById('favorites-container');
  const spinner = document.getElementById('favorites-loading');
  if (!favoritesContainer || !spinner) return;

  try {
    spinner.classList.remove('hidden');
    favoritesContainer.innerHTML = '';

    const response = await fetch('/api/favorites');
    if (!response.ok) throw new Error('Failed to load favorites');

    const data = await response.json();

    if (!data.favorites || data.favorites.length === 0) {
      favoritesContainer.innerHTML = '<div class="text-gray-500 text-center p-4">You haven\'t favorited any designs yet.</div>';
      return;
    }

    data.favorites.forEach(favorite => {
      const card = document.createElement('div');
      card.className = 'bg-white rounded-lg shadow-md overflow-hidden';
      card.innerHTML = `
        <img src="${favorite.image_url}" alt="Favorite design" loading="lazy" class="w-full h-48 object-cover" />
        <div class="p-3">
          <p class="text-sm text-gray-600 line-clamp-2">${favorite.prompt || 'No description'}</p>
          <div class="flex justify-between mt-2">
            <span class="text-xs text-gray-500">${new Date(favorite.timestamp).toLocaleDateString()}</span>
            <div class="flex gap-2">
              <button class="download-button bg-blue-500 text-white px-2 py-1 rounded text-xs hover:bg-blue-600"
                      data-image-url="${favorite.image_url}">
                <i class="fas fa-download mr-1"></i> Download
              </button>
              <button class="favorite-button bg-green-500 text-white px-2 py-1 rounded text-xs hover:bg-green-600"
                      data-image="${favorite.image_url}" data-prompt="${favorite.prompt || ''}" data-favorite-id="${favorite.id}">
                <i class="fas fa-check"></i> Favorited
              </button>
              <button class="remove-favorite text-red-500 text-sm" data-id="${favorite.id}">
                <i class="fas fa-trash"></i> Remove
              </button>
            </div>
          </div>
        </div>
      `;
      favoritesContainer.appendChild(card);
    });
    initializeFavoriteButtons();
    setupDownloadButtons();
    document.querySelectorAll('.remove-favorite').forEach(button => {
      button.addEventListener('click', async function () {
        const favoriteId = this.dataset.id;
        try {
          const response = await fetch(`/api/favorites/${favoriteId}`, { method: 'DELETE' });
          if (!response.ok) throw new Error('Failed to remove favorite');
          this.closest('.bg-white').remove();

          if (favoritesContainer.children.length === 0) {
            favoritesContainer.innerHTML = '<div class="text-gray-500 text-center p-4">You haven\'t favorited any designs yet.</div>';
          }
        } catch (error) {
          console.error('Error removing favorite:', error);
          alert('Failed to remove favorite');
        }
      });
    });

  } catch (error) {
    console.error('Error loading favorites:', error);
    favoritesContainer.innerHTML = '<div class="text-red-500 text-center p-4">Failed to load favorites. Please try again.</div>';
  } finally {
    spinner.classList.add('hidden');
  }
}
/**
 * Loads the user's image ratings and renders them in the profile ratings tab.
 */
async function loadRatings() {
    const ratingsContainer = document.getElementById('ratings-container');
    if (!ratingsContainer) return;
  
    try {
      ratingsContainer.innerHTML = '<div class="loading-spinner">Loading ratings...</div>';
  
      const response = await fetchWithRetry('/api/ratings');
      if (!response.ok) {
        throw new Error('Failed to load ratings');
      }
  
      const data = await response.json();
  
      if (!data.ratings || data.ratings.length === 0) {
        ratingsContainer.innerHTML = '<div class="text-gray-500 text-center p-4">You haven\'t rated any designs yet.</div>';
        return;
      }
  
      // Render ratings grid
      ratingsContainer.innerHTML = '';
      data.ratings.forEach(rating => {
        const ratingCard = document.createElement('div');
        ratingCard.className = 'bg-white rounded-lg shadow-md overflow-hidden';
        ratingCard.innerHTML = `
          <img src="${rating.image_url}" alt="Rated design" class="w-full h-48 object-cover" />
          <div class="p-3">
            <div class="flex items-center mb-1">
              <span class="text-xs mr-1">Relevance:</span>
              ${generateStaticStars(rating.prompt_relevance)}
            </div>
            <div class="flex items-center mb-1">
              <span class="text-xs mr-1">Quality:</span>
              ${generateStaticStars(rating.image_quality)}
            </div>
            <div class="flex items-center mb-1">
              <span class="text-xs mr-1">Style:</span>
              ${generateStaticStars(rating.style_accuracy)}
            </div>
            <div class="flex justify-between mt-2">
              <span class="text-xs text-gray-500">${new Date(rating.created_at).toLocaleDateString()}</span>
            </div>
          </div>
        `;
        ratingsContainer.appendChild(ratingCard);
      });
    } catch (error) {
      console.error('Error loading ratings:', error);
      ratingsContainer.innerHTML = '<div class="text-red-500 text-center p-4">Failed to load ratings. Please try again.</div>';
    }
  }
  
/**
 * Generates HTML for static star ratings.
 * Filled stars represent the rating value; empty stars for the rest.
 * 
 * @param {number} rating - Rating value from 1 to 5
 * @returns {string} HTML string containing star icons
 */
function generateStaticStars(rating) {
    let html = '';
    for (let i = 1; i <= 5; i++) {
      if (i <= rating) {
        html += '<i class="fas fa-star text-yellow-500 text-xs"></i>';
      } else {
        html += '<i class="far fa-star text-gray-300 text-xs"></i>';
      }
    }
    return html;
  }

function addEventListenerOnce(element, event, handler) {
  if (!element.dataset.listenerAttached) {
    element.addEventListener(event, handler);
    element.dataset.listenerAttached = "true";
  }
}

const chatMessages = document.getElementById('chat-messages');
if (chatMessages) {
  chatMessages.addEventListener('click', async (event) => {
    const target = event.target;

    // Favorite toggle (defensive: require expected dataset)
    const favoriteBtn = target.closest('.favorite-button');
    if (favoriteBtn && favoriteBtn.dataset.image) {
      event.preventDefault();
      if (favoriteBtn.disabled) return;
      try {
        await toggleFavorite(favoriteBtn);
      } catch (err) {
        console.error('Favorite toggle failed:', err);
        showError('Failed to update favorite.');
      }
      return;
    }

    // (If you add more delegated features here, also validate their data-* attributes)
  });
}

function scrollToMessageIfNeeded() {
  const urlParams = new URLSearchParams(window.location.search);
  const scrollToId = urlParams.get('scroll_to_id');
  if (scrollToId) {
    const el = document.getElementById(scrollToId);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.classList.add('ring-2', 'ring-orange-500', 'rounded-md', 'transition');
      setTimeout(() => {
        el.classList.remove('ring-2', 'ring-orange-500', 'rounded-md', 'transition');
      }, 2000);
    }
  }
}

window.addEventListener('load', function () {
  scrollToMessageIfNeeded();
});

function setupStarClickListeners() {
  document.querySelectorAll('.star-icon').forEach(icon => {
    icon.addEventListener('click', function () {
      const selectedRating = parseInt(this.dataset.rating);
      const category = this.dataset.category;
      const container = this.closest('.star-rating');
      if (!container || !category) return;

      // Highlight selected stars
      container.querySelectorAll('.star-icon').forEach(star => {
        const starRating = parseInt(star.dataset.rating);
        if (starRating <= selectedRating) {
          star.classList.add('fas', 'text-yellow-500');
          star.classList.remove('far');
        } else {
          star.classList.remove('fas', 'text-yellow-500');
          star.classList.add('far');
        }
      });

      // Save selected value in container
      container.dataset[`${category}Rating`] = selectedRating;
    });
  });
}
