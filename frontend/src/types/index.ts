export interface JobStatus {
  job_id: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  progress: number;
  message: string;
  result?: any;
  error?: string;
}

export interface AnalysisResult {
  sections: Record<string, Record<string, {
    allowed: boolean | null; // null = manual approval required
    confidence?: number | null; // 0.0-1.0 confidence score for the match
    note: string;
    evidence: {
      text: string;
      page?: number;
    };
  }>>; // All sections are flat (future, option, warrant are top-level, no parent "derivatives" category)
  total_instruments: number;
  allowed_instruments: number;
  evidence_coverage: number;
  confidence_score: number;
  processing_time: number;
  trace_id?: string;
}

export interface Settings {
  analysisMethod: 'keywords' | 'llm' | 'llm_with_fallback';
  llmProvider: 'openai' | 'ollama';
  model: string;
  fundId: string;
}

export interface AnalysisRequest {
  file_path: string;
  analysis_method: string;
  llm_provider: string;
  model: string;
  fund_id: string;
}

// Type for instrument data structure
export interface InstrumentData {
  allowed: boolean | null;
  confidence?: number | null;
  note: string;
  evidence: {
    text: string;
    page?: number;
  };
}
