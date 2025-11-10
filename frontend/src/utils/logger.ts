/**
 * Frontend logging utility for structured logging
 * Logs all API requests and responses for debugging
 * Supports log persistence in memory and localStorage, and file download
 */

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export interface LogEntry {
  timestamp: string;
  level: LogLevel;
  message: string;
  context?: Record<string, any>;
  requestId?: string;
}

class Logger {
  private enabled: boolean = true;
  private logLevel: LogLevel = 'info';
  private logStorage: LogEntry[] = [];
  private maxLogEntries: number = 1000; // Maximum log entries to keep in memory
  private persistLogs: boolean = true; // Whether to persist logs to localStorage
  private readonly STORAGE_KEY = 'frontend_logs';
  private readonly MAX_STORAGE_SIZE = 5 * 1024 * 1024; // 5MB max localStorage size

  constructor() {
    // Enable logging in development, or if explicitly enabled
    this.enabled = process.env.NODE_ENV === 'development' || 
                   localStorage.getItem('enableLogging') === 'true';
    
    // Set log level from localStorage or default
    const savedLevel = localStorage.getItem('logLevel') as LogLevel;
    if (savedLevel && ['debug', 'info', 'warn', 'error'].includes(savedLevel)) {
      this.logLevel = savedLevel;
    }

    // Load persisted logs from localStorage
    this.loadPersistedLogs();
  }

  private shouldLog(level: LogLevel): boolean {
    if (!this.enabled) return false;
    
    const levels: LogLevel[] = ['debug', 'info', 'warn', 'error'];
    return levels.indexOf(level) >= levels.indexOf(this.logLevel);
  }

  private formatMessage(level: LogLevel, message: string, context?: Record<string, any>, requestId?: string): string {
    const timestamp = new Date().toISOString();
    const emoji = {
      debug: '🔍',
      info: '📘',
      warn: '⚠️',
      error: '❌'
    }[level];

    let formatted = `${emoji} [${timestamp}] [${level.toUpperCase()}] ${message}`;
    
    if (requestId) {
      formatted += ` [${requestId}]`;
    }
    
    if (context) {
      formatted += `\n${JSON.stringify(context, null, 2)}`;
    }
    
    return formatted;
  }

  private log(level: LogLevel, message: string, context?: Record<string, any>, requestId?: string) {
    if (!this.shouldLog(level)) return;

    const formatted = this.formatMessage(level, message, context, requestId);
    
    // Create log entry
    const logEntry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      message,
      context,
      requestId
    };

    // Store in memory
    this.logStorage.push(logEntry);
    
    // Limit memory storage size
    if (this.logStorage.length > this.maxLogEntries) {
      this.logStorage.shift(); // Remove oldest entry
    }

    // Persist to localStorage if enabled
    if (this.persistLogs) {
      this.persistLog(logEntry);
    }
    
    // Output to console
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
    }
  }

  debug(message: string, context?: Record<string, any>, requestId?: string) {
    this.log('debug', message, context, requestId);
  }

  info(message: string, context?: Record<string, any>, requestId?: string) {
    this.log('info', message, context, requestId);
  }

  warn(message: string, context?: Record<string, any>, requestId?: string) {
    this.log('warn', message, context, requestId);
  }

  error(message: string, context?: Record<string, any>, requestId?: string) {
    this.log('error', message, context, requestId);
  }

  // API request logging
  logRequest(method: string, url: string, data?: any, headers?: Record<string, string>) {
    const requestId = this.generateRequestId();
    this.info(`📤 OUTGOING REQUEST ${method} ${url}`, {
      method,
      url,
      data: this.sanitizeData(data),
      headers: this.sanitizeHeaders(headers)
    }, requestId);
    return requestId;
  }

  logResponse(method: string, url: string, status: number, data?: any, duration?: number, requestId?: string) {
    const level: LogLevel = status >= 400 ? 'error' : 'info';
    const emoji = status >= 400 ? '❌' : '📥';
    this.log(level, `${emoji} INCOMING RESPONSE ${method} ${url} | Status: ${status}${duration ? ` | Duration: ${duration}ms` : ''}`, {
      method,
      url,
      status,
      data: this.sanitizeData(data),
      duration
    }, requestId);
  }

  logError(method: string, url: string, error: any, requestId?: string) {
    this.error(`❌ REQUEST ERROR ${method} ${url}`, {
      method,
      url,
      error: {
        message: error.message,
        status: error.response?.status,
        data: error.response?.data,
        stack: error.stack
      }
    }, requestId);
  }

  private sanitizeData(data: any): any {
    if (!data) return data;
    
    if (typeof data === 'object') {
      const sanitized = { ...data };
      const sensitiveKeys = ['password', 'api_key', 'token', 'authorization', 'secret', 'access_token'];
      
      for (const key in sanitized) {
        if (sensitiveKeys.some(sk => key.toLowerCase().includes(sk.toLowerCase()))) {
          sanitized[key] = '***MASKED***';
        } else if (typeof sanitized[key] === 'object') {
          sanitized[key] = this.sanitizeData(sanitized[key]);
        }
      }
      
      return sanitized;
    }
    
    return data;
  }

  private sanitizeHeaders(headers?: Record<string, string>): Record<string, string> | undefined {
    if (!headers) return headers;
    
    const sanitized = { ...headers };
    const sensitiveKeys = ['authorization', 'x-api-key', 'cookie'];
    
    for (const key in sanitized) {
      if (sensitiveKeys.some(sk => key.toLowerCase().includes(sk.toLowerCase()))) {
        sanitized[key] = '***MASKED***';
      }
    }
    
    return sanitized;
  }

  private generateRequestId(): string {
    return `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  enable() {
    this.enabled = true;
    localStorage.setItem('enableLogging', 'true');
  }

  disable() {
    this.enabled = false;
    localStorage.setItem('enableLogging', 'false');
  }

  setLevel(level: LogLevel) {
    this.logLevel = level;
    localStorage.setItem('logLevel', level);
  }

  // Log persistence methods
  private persistLog(entry: LogEntry) {
    try {
      const existingLogs = this.getPersistedLogs();
      existingLogs.push(entry);
      
      // Keep only recent logs (last 500 entries) to avoid localStorage overflow
      const recentLogs = existingLogs.slice(-500);
      
      const logsJson = JSON.stringify(recentLogs);
      
      // Check if we're approaching localStorage size limit
      if (logsJson.length > this.MAX_STORAGE_SIZE * 0.9) {
        // Keep only most recent 200 entries
        const trimmedLogs = recentLogs.slice(-200);
        localStorage.setItem(this.STORAGE_KEY, JSON.stringify(trimmedLogs));
      } else {
        localStorage.setItem(this.STORAGE_KEY, logsJson);
      }
    } catch (e) {
      // If localStorage is full or unavailable, just continue without persistence
      console.warn('Could not persist log to localStorage:', e);
    }
  }

  private loadPersistedLogs() {
    try {
      const persisted = localStorage.getItem(this.STORAGE_KEY);
      if (persisted) {
        const logs = JSON.parse(persisted) as LogEntry[];
        // Load last 100 entries into memory
        this.logStorage = logs.slice(-100);
      }
    } catch (e) {
      console.warn('Could not load persisted logs:', e);
    }
  }

  private getPersistedLogs(): LogEntry[] {
    try {
      const persisted = localStorage.getItem(this.STORAGE_KEY);
      if (persisted) {
        return JSON.parse(persisted) as LogEntry[];
      }
    } catch (e) {
      console.warn('Could not retrieve persisted logs:', e);
    }
    return [];
  }

  // Public methods for log management
  getLogs(level?: LogLevel, limit?: number): LogEntry[] {
    let logs = [...this.logStorage];
    
    // If we want more logs, get from localStorage
    if (limit && limit > this.logStorage.length) {
      const persisted = this.getPersistedLogs();
      logs = [...persisted];
    }
    
    // Filter by level if specified
    if (level) {
      logs = logs.filter(log => log.level === level);
    }
    
    // Apply limit
    if (limit) {
      logs = logs.slice(-limit);
    }
    
    return logs;
  }

  getErrorLogs(limit?: number): LogEntry[] {
    return this.getLogs('error', limit);
  }

  clearLogs() {
    this.logStorage = [];
    try {
      localStorage.removeItem(this.STORAGE_KEY);
    } catch (e) {
      console.warn('Could not clear persisted logs:', e);
    }
  }

  downloadLogs(filename?: string) {
    const logs = this.getPersistedLogs();
    if (logs.length === 0) {
      console.warn('No logs to download');
      return;
    }

    // Format logs as text
    const logText = logs.map(entry => {
      const contextStr = entry.context ? `\n${JSON.stringify(entry.context, null, 2)}` : '';
      const requestIdStr = entry.requestId ? ` [${entry.requestId}]` : '';
      return `[${entry.timestamp}] [${entry.level.toUpperCase()}]${requestIdStr} ${entry.message}${contextStr}`;
    }).join('\n\n');

    // Create blob and download
    const blob = new Blob([logText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || `frontend_logs_${new Date().toISOString().replace(/[:.]/g, '-')}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  downloadErrorLogs(filename?: string) {
    const errorLogs = this.getErrorLogs();
    if (errorLogs.length === 0) {
      console.warn('No error logs to download');
      return;
    }

    const logText = errorLogs.map(entry => {
      const contextStr = entry.context ? `\n${JSON.stringify(entry.context, null, 2)}` : '';
      const requestIdStr = entry.requestId ? ` [${entry.requestId}]` : '';
      return `[${entry.timestamp}] [${entry.level.toUpperCase()}]${requestIdStr} ${entry.message}${contextStr}`;
    }).join('\n\n');

    const blob = new Blob([logText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || `frontend_error_logs_${new Date().toISOString().replace(/[:.]/g, '-')}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  setPersistLogs(enabled: boolean) {
    this.persistLogs = enabled;
    localStorage.setItem('persistLogs', enabled.toString());
  }

  getLogStats() {
    const logs = this.getPersistedLogs();
    return {
      total: logs.length,
      inMemory: this.logStorage.length,
      byLevel: {
        debug: logs.filter(l => l.level === 'debug').length,
        info: logs.filter(l => l.level === 'info').length,
        warn: logs.filter(l => l.level === 'warn').length,
        error: logs.filter(l => l.level === 'error').length,
      },
      oldest: logs.length > 0 ? logs[0].timestamp : null,
      newest: logs.length > 0 ? logs[logs.length - 1].timestamp : null
    };
  }
}

// Export singleton instance
export const logger = new Logger();

