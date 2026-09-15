import {
  SSEConnectionStatus,
  SSEEventPayload,
  SSEEventType
} from '../types';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export type SSEHandler = (event: string, data: SSEEventPayload) => void;
export type SSEConnectionHandler = (status: SSEConnectionStatus) => void;

export class WorkflowEventSource {
  private eventSource: EventSource | null = null;
  private rfpId: string;
  private onMessage: SSEHandler;
  private onConnectionChange?: SSEConnectionHandler;
  private reconnectTimer: number | null = null;
  private retryCount: number = 0;
  private maxRetries: number = 5;
  private isExplicitlyClosed: boolean = false;

  constructor(
    rfpId: string,
    onMessage: SSEHandler,
    onConnectionChange?: SSEConnectionHandler
  ) {
    this.rfpId = rfpId;
    this.onMessage = onMessage;
    this.onConnectionChange = onConnectionChange;
  }

  connect() {
    this.isExplicitlyClosed = false;

    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }

    const url = `${API_BASE}/api/workflow/${this.rfpId}/stream`;
    this.onConnectionChange?.('reconnecting');

    try {
      this.eventSource = new EventSource(url);

      this.eventSource.onopen = () => {
        this.retryCount = 0;
        this.onConnectionChange?.('connected');
      };

      const eventTypes: SSEEventType[] = [
        'status_change',
        'node_completed',
        'human_approval_required',
        'workflow_finished',
        'error'
      ];

      eventTypes.forEach((type) => {
        this.eventSource?.addEventListener(type, (e: MessageEvent) => {
          try {
            const parsed: SSEEventPayload = JSON.parse(e.data);
            if (parsed && typeof parsed === 'object') {
              this.onMessage(type, parsed);

              if (type === 'workflow_finished') {
                this.onConnectionChange?.('completed');
                this.close();
              } else if (type === 'error') {
                this.onConnectionChange?.('failed');
                this.close();
              }
            }
          } catch (err) {
            console.error('[SSE Event Parse Error]', err);
          }
        });
      });

      this.eventSource.onerror = (err) => {
        if (this.isExplicitlyClosed) return;

        if (this.eventSource?.readyState === EventSource.CLOSED) {
          if (this.retryCount < this.maxRetries) {
            this.retryCount += 1;
            this.onConnectionChange?.('reconnecting');
            const delay = Math.min(1000 * Math.pow(1.5, this.retryCount), 8000);
            this.reconnectTimer = window.setTimeout(() => {
              if (!this.isExplicitlyClosed) {
                this.connect();
              }
            }, delay);
          } else {
            this.onConnectionChange?.('disconnected');
            this.close();
          }
        } else {
          this.onConnectionChange?.('reconnecting');
        }
      };
    } catch (err) {
      console.error('[SSE Connection Error]', err);
      this.onConnectionChange?.('failed');
    }
  }

  close() {
    this.isExplicitlyClosed = true;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }
}
