/**
 * Frontend logging utility for structured logging
 * Logs all API requests and responses for debugging
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  message: string;
  context?: Record<string, any>;
  requestId?: string;
}

class Logger {
  private enabled: boolean = true;
  private logLevel: LogLevel = 'info';

  constructor() {
    // Enable logging in development, or if explicitly enabled
    this.enabled = process.env.NODE_ENV === 'development' || 
                   localStorage.getItem('enableLogging') === 'true';
    
    // Set log level from localStorage or default
    const savedLevel = localStorage.getItem('logLevel') as LogLevel;
    if (savedLevel && ['debug', 'info', 'warn', 'error'].includes(savedLevel)) {
      this.logLevel = savedLevel;
    }
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
}

// Export singleton instance
export const logger = new Logger();

