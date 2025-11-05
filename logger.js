/**
 * Node.js logging utility for the Express server
 * Provides structured logging with file and console handlers
 */

const fs = require('fs');
const path = require('path');

class Logger {
  constructor() {
    this.enabled = true;
    this.logLevel = process.env.LOG_LEVEL || 'info';
    
    // Try to create logs directory
    this.logDir = path.join(__dirname, 'logs');
    try {
      if (!fs.existsSync(this.logDir)) {
        fs.mkdirSync(this.logDir, { recursive: true });
      }
    } catch (e) {
      // If we can't create logs directory, just use console
      this.logDir = null;
    }
    
    this.logFile = this.logDir ? path.join(this.logDir, 'server.log') : null;
    this.errorLogFile = this.logDir ? path.join(this.logDir, 'error.log') : null;
  }

  shouldLog(level) {
    if (!this.enabled) return false;
    
    const levels = ['debug', 'info', 'warn', 'error'];
    return levels.indexOf(level) >= levels.indexOf(this.logLevel);
  }

  formatMessage(level, message, context, requestId) {
    const timestamp = new Date().toISOString();
    const emoji = {
      debug: '🔍',
      info: '📘',
      warn: '⚠️',
      error: '❌'
    }[level] || '';

    let formatted = `${emoji} [${timestamp}] [${level.toUpperCase()}]`;
    
    if (requestId) {
      formatted += ` [${requestId}]`;
    }
    
    formatted += ` ${message}`;
    
    if (context) {
      formatted += ` ${typeof context === 'string' ? context : JSON.stringify(context, null, 2)}`;
    }
    
    return formatted;
  }

  writeToFile(level, message, context, requestId) {
    if (!this.logFile) return;
    
    const formatted = this.formatMessage(level, message, context, requestId);
    const logLine = `${formatted}\n`;
    
    try {
      // Write to main log file
      if (level !== 'error' && this.logFile) {
        fs.appendFileSync(this.logFile, logLine, 'utf8');
      }
      
      // Write to error log file
      if (level === 'error' && this.errorLogFile) {
        fs.appendFileSync(this.errorLogFile, logLine, 'utf8');
      }
    } catch (e) {
      // If file writing fails, just continue (don't break the app)
    }
  }

  log(level, message, context, requestId) {
    if (!this.shouldLog(level)) return;

    const formatted = this.formatMessage(level, message, context, requestId);
    
    // Write to console
    switch (level) {
      case 'debug':
        console.debug(formatted);
        break;
      case 'info':
        console.info(formatted);
        break;
      case 'warn':
        console.warn(formatted);
        break;
      case 'error':
        console.error(formatted);
        break;
      default:
        console.log(formatted);
    }
    
    // Write to file
    this.writeToFile(level, message, context, requestId);
  }

  debug(message, context, requestId) {
    this.log('debug', message, context, requestId);
  }

  info(message, context, requestId) {
    this.log('info', message, context, requestId);
  }

  warn(message, context, requestId) {
    this.log('warn', message, context, requestId);
  }

  error(message, context, requestId) {
    this.log('error', message, context, requestId);
  }
}

// Export singleton instance
module.exports = new Logger();

