import { AfterViewChecked, Component, ElementRef, OnDestroy, ViewChild, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { A11yModule } from '@angular/cdk/a11y';
import { FormsModule } from '@angular/forms';
import { SHELL_PAGE_VM } from '../../shell-page.types';
import type { ShellPageVm } from '../../shell-page.types';
import { BackendApiService } from '../../../../core/backend-api.service';
import type { UsageModelBreakdownResponse, UsageRow, UsageScopeKey } from '../../../../core/backend-api.service';
import type { Chart, Options } from 'highcharts';
import { firstValueFrom } from 'rxjs';

type UsageSortKey = 'model' | 'input' | 'cachedInput' | 'reasoning' | 'output' | 'total' | 'cost' | 'tokenSharePct' | 'costSharePct';
type HistoryViewMode = 'table' | 'visual';
type VisualScope = 'session' | 'today' | 'week' | 'month' | 'all_time';

@Component({
  selector: 'app-shell-usage-panel',
  standalone: true,
  imports: [CommonModule, A11yModule, FormsModule],
  templateUrl: './usage-panel.component.html',
})
export class ShellUsagePanelComponent implements AfterViewChecked, OnDestroy {
  readonly vm = inject(SHELL_PAGE_VM) as ShellPageVm;
  private readonly api = inject(BackendApiService);
  @ViewChild('tokenVisualChart') tokenVisualChart?: ElementRef<HTMLDivElement>;
  @ViewChild('tokenCostVisualChart') tokenCostVisualChart?: ElementRef<HTMLDivElement>;
  @ViewChild('modelBreakdownTokenChart') modelBreakdownTokenChart?: ElementRef<HTMLDivElement>;
  @ViewChild('modelBreakdownCostChart') modelBreakdownCostChart?: ElementRef<HTMLDivElement>;

  filterQuery = '';
  sortKey: UsageSortKey = 'cost';
  sortDirection: 'asc' | 'desc' = 'desc';
  historyViewMode: HistoryViewMode = 'table';
  selectedModelName = '';
  modelBreakdownData: UsageModelBreakdownResponse | null = null;
  modelBreakdownLoading = false;
  modelBreakdownError = '';
  private _highcharts?: typeof import('highcharts');
  private _tokenChart?: Chart;
  private _costChart?: Chart;
  private _modelBreakdownTokenChart?: Chart;
  private _modelBreakdownCostChart?: Chart;
  private _pendingChartRender = false;
  private _pendingModelBreakdownRender = false;
  private _chartRenderInFlight = false;
  private _modelBreakdownRenderInFlight = false;
  private _lastChartSignature = '';
  private _lastModelBreakdownSignature = '';

  setFilterQuery(value: string): void {
    this.filterQuery = String(value || '').trimStart();
    this._queueChartRender();
  }

  setSort(nextKey: UsageSortKey): void {
    if (this.sortKey === nextKey) {
      this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
      this._queueChartRender();
      return;
    }
    this.sortKey = nextKey;
    this.sortDirection = nextKey === 'model' ? 'asc' : 'desc';
    this._queueChartRender();
  }

  sortIndicator(key: UsageSortKey): string {
    if (this.sortKey !== key) return '';
    return this.sortDirection === 'asc' ? '↑' : '↓';
  }

  tokenHistoryRows(): UsageRow[] {
    const scope = this.vm.tokenHistoryScope(this.vm.tokenHistoryTab());
    return this._rowsForScope(scope?.rows);
  }

  tokenHistoryVisualRows(): UsageRow[] {
    const scope = this.vm.tokenHistoryScope(this.vm.tokenHistoryTab());
    return this._rowsForScope(scope?.rows);
  }

  setHistoryViewMode(mode: HistoryViewMode): void {
    if (this.historyViewMode === mode) return;
    this.historyViewMode = mode;
    this._queueChartRender();
  }

  isHistoryViewMode(mode: HistoryViewMode): boolean {
    return this.historyViewMode === mode;
  }

  visualScopeValue(): VisualScope {
    return this.vm.tokenHistoryTab();
  }

  setVisualScope(value: string): void {
    this.selectScope(value);
  }

  visualScopeTitle(): string {
    return this.vm.tokenHistoryScopeTitle(this.vm.tokenHistoryTab());
  }

  tokenHistorySummaryModelCount(): number {
    if (this.isHistoryViewMode('visual')) {
      return this.tokenHistoryVisualRows().length;
    }
    return this.tokenHistoryRows().length;
  }

  tokenHistorySummaryCost(): string {
    if (!this.isHistoryViewMode('visual')) {
      return this.vm.tokenHistoryScopeTotalDisplay(this.vm.tokenHistoryTab());
    }
    const scope = this.vm.tokenHistoryScope(this.vm.tokenHistoryTab());
    return scope?.totals?.costDisplay || '$0.000000';
  }

  selectScope(value: string): void {
    const next = String(value || '').trim().toLowerCase();
    if (next !== 'session' && next !== 'today' && next !== 'week' && next !== 'month' && next !== 'all_time') return;
    this.vm.setTokenHistoryTab(next);
    this._queueChartRender();
    if (this.selectedModelName) {
      void this.openModelBreakdown(this.selectedModelName);
    }
  }

  async openModelBreakdown(model: string): Promise<void> {
    const modelName = String(model || '').trim();
    if (!modelName) return;
    this.selectedModelName = modelName;
    this.modelBreakdownLoading = true;
    this.modelBreakdownError = '';
    const scope = this.vm.tokenHistoryTab() as UsageScopeKey;
    const sessionId = scope === 'session' ? (this.vm.selectedSessionId() || undefined) : undefined;
    try {
      const payload = await firstValueFrom(this.api.getUsageModelBreakdown(scope, modelName, sessionId));
      this.modelBreakdownData = payload || null;
      if (this.historyViewMode === 'visual') {
        this._pendingModelBreakdownRender = true;
      }
    } catch (error: unknown) {
      const message = String((error as { message?: string })?.message || 'Failed to load model breakdown.');
      this.modelBreakdownData = null;
      this.modelBreakdownError = message;
    } finally {
      this.modelBreakdownLoading = false;
    }
  }

  clearModelBreakdown(): void {
    this.selectedModelName = '';
    this.modelBreakdownData = null;
    this.modelBreakdownError = '';
    this.modelBreakdownLoading = false;
    if (this._modelBreakdownTokenChart) {
      this._modelBreakdownTokenChart.destroy();
      this._modelBreakdownTokenChart = undefined;
    }
    if (this._modelBreakdownCostChart) {
      this._modelBreakdownCostChart.destroy();
      this._modelBreakdownCostChart = undefined;
    }
    this._lastModelBreakdownSignature = '';
  }

  ngAfterViewChecked(): void {
    if (this.historyViewMode === 'visual' && this.vm.showTokenHistoryModal() && (!this._tokenChart || !this._costChart)) {
      this._pendingChartRender = true;
    }
    if (
      this.historyViewMode === 'visual'
      && this.selectedModelName
      && this.modelBreakdownData
      && (!this._modelBreakdownTokenChart || !this._modelBreakdownCostChart)
    ) {
      this._pendingModelBreakdownRender = true;
    }
    if (this._pendingChartRender) {
      this._pendingChartRender = false;
      void this._renderVisualChart();
    }
    if (this._pendingModelBreakdownRender) {
      this._pendingModelBreakdownRender = false;
      void this._renderModelBreakdownCharts();
    }
  }

  ngOnDestroy(): void {
    this._destroyChart();
  }

  private _rowsForScope(scopeRows: UsageRow[] | null | undefined): UsageRow[] {
    const rows = Array.isArray(scopeRows) ? [...scopeRows] : [];
    const filter = this.filterQuery.trim().toLowerCase();
    const filtered = !filter
      ? rows
      : rows.filter((row) => String(row.model || '').toLowerCase().includes(filter));
    const directionFactor = this.sortDirection === 'asc' ? 1 : -1;
    filtered.sort((a, b) => {
      if (this.sortKey === 'model') {
        return String(a.model || '').localeCompare(String(b.model || '')) * directionFactor;
      }
      const left = this._numericSortValue(a, this.sortKey);
      const right = this._numericSortValue(b, this.sortKey);
      if (left === right) return 0;
      return (left < right ? -1 : 1) * directionFactor;
    });
    return filtered;
  }

  private _queueChartRender(): void {
    if (!this.vm.showTokenHistoryModal()) {
      this._destroyChart();
      return;
    }
    this._pendingChartRender = true;
  }

  private async _renderVisualChart(): Promise<void> {
    if (this._chartRenderInFlight) return;
    this._chartRenderInFlight = true;
    try {
      if (!this.vm.showTokenHistoryModal() || this.historyViewMode !== 'visual' || this.vm.loadingUsage()) {
        this._destroyChart();
        return;
      }
      const tokenContainer = this.tokenVisualChart?.nativeElement;
      const costContainer = this.tokenCostVisualChart?.nativeElement;
      if (!tokenContainer || !costContainer) return;

      const rows = this.tokenHistoryVisualRows();
      if (rows.length === 0) {
        this._destroyChart();
        return;
      }
      const signature = JSON.stringify(
        rows.map((row) => [row.model, row.input ?? 0, row.reasoning ?? 0, row.output ?? 0, row.cost ?? 0]),
      );
      if (signature === this._lastChartSignature && this._tokenChart && this._costChart) return;
      this._lastChartSignature = signature;

      if (!this._highcharts) {
        const highchartsModule = await import('highcharts');
        this._highcharts = (highchartsModule.default ?? highchartsModule) as typeof import('highcharts');
        try {
          const highcharts3dModule = await import('highcharts/highcharts-3d');
          const moduleFactory = (highcharts3dModule.default ?? highcharts3dModule) as unknown as ((H: typeof import('highcharts')) => void) | undefined;
          if (typeof moduleFactory === 'function') {
            moduleFactory(this._highcharts);
          }
        } catch {
          // Keep token chart functional even if 3D module fails to load.
        }
        try {
          const variablePieModule = await import('highcharts/modules/variable-pie');
          const moduleFactory = (variablePieModule.default ?? variablePieModule) as unknown as ((H: typeof import('highcharts')) => void) | undefined;
          if (typeof moduleFactory === 'function') {
            moduleFactory(this._highcharts);
          }
        } catch {
          // Keep charts functional even if variable pie module fails to load.
        }
      }

      this._destroyChart();
      const categories = rows.map((row) => String(row.model || 'Unknown'));
      const tokenChartOptions: Options = {
        chart: {
          type: 'column',
          backgroundColor: 'transparent',
        },
        title: {
          text: `${this.visualScopeTitle()} — Tokens`,
        },
        credits: {
          enabled: false,
        },
        legend: {
          enabled: false,
        },
        xAxis: {
          categories,
          title: { text: 'Model' },
        },
        yAxis: {
          title: { text: 'Tokens' },
          min: 0,
        },
        tooltip: {
          shared: true,
        },
        plotOptions: {
          series: {
            borderWidth: 0,
            animation: false,
            point: {
              events: {
                click: (event): void => {
                  const modelName = String(event.point.category || '').trim();
                  if (modelName) {
                    void this.openModelBreakdown(modelName);
                  }
                },
              },
            },
            states: {
              inactive: {
                enabled: false,
              },
              hover: {
                enabled: false,
              },
            },
          },
        },
        series: [
          {
            type: 'column',
            name: 'Input',
            data: rows.map((row) => Number(row.input ?? 0)),
            color: '#5B8FF9',
          },
          {
            type: 'column',
            name: 'Reasoning',
            data: rows.map((row) => Number(row.reasoning ?? 0)),
            color: '#61DDAA',
          },
          {
            type: 'column',
            name: 'Output',
            data: rows.map((row) => Number(row.output ?? 0)),
            color: '#65789B',
          },
        ],
      };

      const costPieOptions: Options = {
        chart: {
          type: 'pie',
          backgroundColor: 'transparent',
          options3d: {
            enabled: true,
            alpha: 45,
            beta: 0,
          },
        },
        title: {
          text: `${this.visualScopeTitle()} — Cost Split`,
        },
        credits: {
          enabled: false,
        },
        tooltip: {
          pointFormat: '<b>{point.name}</b><br/>Cost: ${point.y:.6f}<br/>Share: {point.percentage:.1f}%',
        },
        plotOptions: {
          pie: {
            allowPointSelect: false,
            animation: false,
            innerSize: '55%',
            depth: 35,
            borderWidth: 1,
            borderColor: '#ffffff',
            point: {
              events: {
                click: (event): void => {
                  const modelName = String(event.point.name || '').trim();
                  if (modelName && modelName !== 'No Cost Data') {
                    void this.openModelBreakdown(modelName);
                  }
                },
              },
            },
            cursor: 'pointer',
            dataLabels: {
              enabled: true,
              format: '{point.name}',
            },
            states: {
              inactive: {
                enabled: false,
              },
              hover: {
                enabled: false,
              },
            },
          },
        },
        series: [
          {
            type: 'pie',
            name: 'Cost',
            data: rows
              .filter((row) => Number(row.cost ?? 0) > 0)
              .map((row) => ({
                name: String(row.model || 'Unknown'),
                y: Number(row.cost ?? 0),
              })),
          },
        ],
      };

      const hasCostPoints = rows.some((row) => Number(row.cost ?? 0) > 0);
      if (!hasCostPoints) {
        costPieOptions.series = [
          {
            type: 'pie',
            name: 'Cost',
            data: [
              {
                name: 'No Cost Data',
                y: 1,
              },
            ],
            dataLabels: {
              enabled: true,
              format: 'No Cost Data',
            },
          },
        ];
      }

      this._tokenChart = this._highcharts.chart(tokenContainer, tokenChartOptions);
      this._costChart = this._highcharts.chart(costContainer, costPieOptions);
    } finally {
      this._chartRenderInFlight = false;
    }
  }

  private _destroyChart(): void {
    if (this._tokenChart) {
      this._tokenChart.destroy();
      this._tokenChart = undefined;
    }
    if (this._costChart) {
      this._costChart.destroy();
      this._costChart = undefined;
    }
    if (this._modelBreakdownTokenChart) {
      this._modelBreakdownTokenChart.destroy();
      this._modelBreakdownTokenChart = undefined;
    }
    if (this._modelBreakdownCostChart) {
      this._modelBreakdownCostChart.destroy();
      this._modelBreakdownCostChart = undefined;
    }
    this._lastChartSignature = '';
    this._lastModelBreakdownSignature = '';
  }

  private async _renderModelBreakdownCharts(): Promise<void> {
    if (this._modelBreakdownRenderInFlight) return;
    this._modelBreakdownRenderInFlight = true;
    try {
      const breakdown = this.modelBreakdownData;
      if (!breakdown || !this.selectedModelName) {
        return;
      }
      const tokenContainer = this.modelBreakdownTokenChart?.nativeElement;
      const costContainer = this.modelBreakdownCostChart?.nativeElement;
      if (!tokenContainer || !costContainer) return;
      if (!this._highcharts) return;

      const buckets = Array.isArray(breakdown.buckets) ? breakdown.buckets : [];
      const signature = JSON.stringify({
        model: this.selectedModelName,
        scope: breakdown.scope,
        buckets: buckets.map((item) => [
          item.timestampLabel,
          item.input ?? 0,
          item.reasoning ?? 0,
          item.output ?? 0,
          item.messageCount ?? 0,
          item.cost ?? 0,
        ]),
      });
      if (signature === this._lastModelBreakdownSignature && this._modelBreakdownTokenChart && this._modelBreakdownCostChart) return;
      this._lastModelBreakdownSignature = signature;

      if (this._modelBreakdownTokenChart) {
        this._modelBreakdownTokenChart.destroy();
        this._modelBreakdownTokenChart = undefined;
      }
      if (this._modelBreakdownCostChart) {
        this._modelBreakdownCostChart.destroy();
        this._modelBreakdownCostChart = undefined;
      }

      const categories = buckets.map((item) => String(item.timestampLabel || ''));
      const tokenBarOptions: Options = {
        chart: {
          type: 'column',
          backgroundColor: 'transparent',
        },
        title: {
          text: `${this.selectedModelName} — Timestamp Token Split`,
        },
        credits: { enabled: false },
        xAxis: {
          categories,
          title: { text: 'Timestamp' },
        },
        yAxis: [
          {
            min: 0,
            title: { text: 'Tokens' },
          },
          {
            min: 0,
            title: { text: 'Messages' },
            opposite: true,
            allowDecimals: false,
            labels: {
              format: '{value:.0f}',
            },
          },
        ],
        tooltip: {
          shared: true,
        },
        plotOptions: {
          series: {
            borderWidth: 0,
            animation: false,
            states: {
              inactive: { enabled: false },
              hover: { enabled: false },
            },
          },
        },
        series: [
          {
            type: 'column',
            name: 'Input',
            yAxis: 0,
            data: buckets.map((item) => Number(item.input ?? 0)),
            color: '#5B8FF9',
          },
          {
            type: 'column',
            name: 'Reasoning',
            yAxis: 0,
            data: buckets.map((item) => Number(item.reasoning ?? 0)),
            color: '#61DDAA',
          },
          {
            type: 'column',
            name: 'Output',
            yAxis: 0,
            data: buckets.map((item) => Number(item.output ?? 0)),
            color: '#65789B',
          },
          {
            type: 'column',
            name: 'Messages',
            yAxis: 1,
            data: buckets.map((item) => Number(item.messageCount ?? 0)),
            color: '#F08C2E',
          },
        ],
      };

      const costPieOptions: Options = {
        chart: {
          type: 'variablepie',
          backgroundColor: 'transparent',
        },
        title: {
          text: `${this.selectedModelName} — Timestamp Cost Split`,
        },
        credits: { enabled: false },
        tooltip: {
          pointFormat: '<b>{point.name}</b><br/>Cost: ${point.y:.6f}<br/>Share: {point.percentage:.1f}%',
        },
        plotOptions: {
          variablepie: {
            animation: false,
            minPointSize: 10,
            zMin: 0,
            dataLabels: {
              enabled: true,
              format: '{point.name}',
            },
            states: {
              inactive: { enabled: false },
              hover: { enabled: false },
            },
          },
        },
        series: [
          {
            type: 'variablepie',
            name: 'Cost',
            data: buckets
              .filter((item) => Number(item.cost ?? 0) > 0)
              .map((item) => ({
                name: String(item.timestampLabel || ''),
                y: Number(item.cost ?? 0),
                z: Number(item.total ?? 0),
              })),
          },
        ],
      };

      if (!buckets.some((item) => Number(item.cost ?? 0) > 0)) {
        costPieOptions.series = [
          {
            type: 'variablepie',
            name: 'Cost',
            data: [{ name: 'No Cost Data', y: 1, z: 1 }],
            dataLabels: { enabled: true, format: 'No Cost Data' },
          },
        ];
      }

      this._modelBreakdownTokenChart = this._highcharts.chart(tokenContainer, tokenBarOptions);
      this._modelBreakdownCostChart = this._highcharts.chart(costContainer, costPieOptions);
    } finally {
      this._modelBreakdownRenderInFlight = false;
    }
  }

  private _numericSortValue(row: UsageRow, key: Exclude<UsageSortKey, 'model'>): number {
    switch (key) {
      case 'input':
        return Number(row.input ?? 0);
      case 'reasoning':
        return Number(row.reasoning ?? 0);
      case 'cachedInput':
        return Number(row.cachedInput ?? 0);
      case 'output':
        return Number(row.output ?? 0);
      case 'total':
        return Number(row.total ?? 0);
      case 'cost':
        return Number(row.cost ?? 0);
      case 'tokenSharePct':
        return Number(row.tokenSharePct ?? 0);
      case 'costSharePct':
        return Number(row.costSharePct ?? 0);
      default:
        return 0;
    }
  }
}
