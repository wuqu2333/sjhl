<template>
  <a-card>
    <a-tabs v-model:activeKey="tab" :tab-position="store.isMobile ? 'top' : 'left'" @change="onTabChange">
      <!-- Tab: 115 账号 -->
      <a-tab-pane key="pan115" tab="115 账号">
        <div class="space-y-4">
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <a-card title="新增 115 账号" size="small">
              <a-form layout="vertical" :model="pan115Form" @finish="submit115Account">
                <a-form-item label="名称"><a-input v-model:value="pan115Form.name" placeholder="我的115账号" /></a-form-item>
                <a-form-item label="Cookie (可选，Open不可用时降级使用)">
                  <a-textarea v-model:value="pan115Form.cookie" :rows="3" />
                </a-form-item>
                <a-form-item label="Access Token (Open API)">
                  <a-input-password v-model:value="pan115Form.accessToken" />
                </a-form-item>
                <a-form-item label="Refresh Token">
                  <a-input-password v-model:value="pan115Form.refreshToken" />
                </a-form-item>
                <a-button type="primary" html-type="submit" block>保存</a-button>
              </a-form>
            </a-card>
            <a-card title="已添加账号" size="small">
              <a-empty v-if="!pan115Accounts.length" description="暂无 115 账号" />
              <a-list :data-source="pan115Accounts">
                <template #renderItem="{ item }">
                  <a-list-item>
                    <a-list-item-meta :title="item.name">
                      <template #description>
                        <a-space>
                          <a-tag v-if="item.hasAccessToken" color="green">Open API</a-tag>
                          <a-tag v-if="item.hasCookie" color="orange">Cookie</a-tag>
                        </a-space>
                      </template>
                    </a-list-item-meta>
                    <a-space>
                      <a-button v-if="item.hasAccessToken" size="small" @click="showUserInfo(item.id)" :loading="infoLoading">用户信息</a-button>
                      <a-button v-if="item.hasCookie" size="small" @click="autoAuth115(item.id)" :loading="authLoading">获取Token</a-button>
                      <a-button danger size="small" @click="remove115Account(item.id)">删除</a-button>
                    </a-space>
                  </a-list-item>
                </template>
              </a-list>
            </a-card>
          </div>
          <a-card title="API 延迟配置" size="small">
            <template #extra>
              <a-tag color="blue">CD2 = Open，115直连 = CK</a-tag>
            </template>
            <a-form layout="vertical" :model="activePan115DelayForm" @finish="savePan115DelaySettings">
              <a-form-item label="模式">
                <a-radio-group v-model:value="pan115DelayMode" button-style="solid">
                  <a-radio-button value="open">CD2 / Open</a-radio-button>
                  <a-radio-button value="cookie">115直连 / CK</a-radio-button>
                </a-radio-group>
              </a-form-item>
              <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                <a-form-item label="全局倍数">
                  <a-input-number v-model:value="activePan115DelayForm.globalMultiplier" :min="0" :precision="2" class="w-full" />
                </a-form-item>
                <a-form-item label="全局延时">
                  <a-input-number v-model:value="activePan115DelayForm.globalDelaySeconds" :min="0" :precision="2" addon-after="秒" class="w-full" />
                </a-form-item>
                <a-form-item label="列表/搜索">
                  <a-input-number v-model:value="activePan115DelayForm.listDelaySeconds" :min="0" :precision="2" addon-after="秒" class="w-full" />
                </a-form-item>
                <a-form-item label="重命名">
                  <a-input-number v-model:value="activePan115DelayForm.renameDelaySeconds" :min="0" :precision="2" addon-after="秒" class="w-full" />
                </a-form-item>
                <a-form-item label="删除">
                  <a-input-number v-model:value="activePan115DelayForm.deleteDelaySeconds" :min="0" :precision="2" addon-after="秒" class="w-full" />
                </a-form-item>
                <a-form-item label="移动/复制/新建">
                  <a-input-number v-model:value="activePan115DelayForm.mutateDelaySeconds" :min="0" :precision="2" addon-after="秒" class="w-full" />
                </a-form-item>
                <a-form-item label="下载链接">
                  <a-input-number v-model:value="activePan115DelayForm.downDelaySeconds" :min="0" :precision="2" addon-after="秒" class="w-full" />
                </a-form-item>
              </div>
              <a-space>
                <a-button @click="resetPan115Delay">重置当前模式</a-button>
                <a-button type="primary" html-type="submit" :loading="savingPan115Delay">保存延迟</a-button>
              </a-space>
            </a-form>
          </a-card>
        </div>
      </a-tab-pane>

      <!-- Tab: 租户连接 -->
      <a-tab-pane key="tenants" tab="租户连接">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <a-card title="新增租户连接" size="small">
            <a-form layout="vertical" :model="tenantForm" @finish="submitTenant">
              <a-form-item label="名称"><a-input v-model:value="tenantForm.name" /></a-form-item>
              <a-form-item label="认证模式"><a-select v-model:value="tenantForm.authMode" :options="authModeOpts" /></a-form-item>
              <a-form-item label="区域"><a-select v-model:value="tenantForm.region" :options="regionOpts" /></a-form-item>
              <a-form-item label="Tenant ID"><a-input v-model:value="tenantForm.tenantId" /></a-form-item>
              <a-form-item label="Client ID"><a-input v-model:value="tenantForm.clientId" /></a-form-item>
              <a-form-item label="Client Secret"><a-input-password v-model:value="tenantForm.clientSecret" /></a-form-item>
              <a-form-item label="Refresh Token">
                <a-space>
                  <a-input-password v-model:value="tenantForm.refreshToken" style="width: 300px" />
                  <a-button @click="startTenantOAuth" :loading="tenantOAuthLoading">获取Token</a-button>
                </a-space>
              </a-form-item>
              <a-form-item label="Root Path"><a-input v-model:value="tenantForm.defaultRootPath" /></a-form-item>
              <a-form-item><a-checkbox v-model:checked="tenantForm.importDocumentsOnly">只导入文档库</a-checkbox></a-form-item>
              <a-button type="primary" html-type="submit" block>保存</a-button>
            </a-form>
          </a-card>
          <a-card title="租户连接列表" size="small">
            <a-list :data-source="store.state?.tenantConnections || []">
              <template #renderItem="{ item }">
                <a-list-item>
                  <a-list-item-meta :title="item.name" :description="item.tenantId" />
                  <a-space>
                    <a-button @click="importTenant(item.id)">发现并导入</a-button>
                    <a-button @click="selectMountTenant(item.id)">按 URL 挂载</a-button>
                    <a-button danger @click="removeTenant(item.id)">删除</a-button>
                  </a-space>
                </a-list-item>
              </template>
            </a-list>
          </a-card>
          <a-card title="按站点 URL 手动挂载 SP" size="small">
            <a-form layout="vertical" :model="tenantMountForm" @finish="mountTenantSite">
              <a-form-item label="租户连接">
                <a-select v-model:value="tenantMountForm.connectionId" :options="tenantConnectionOptions" placeholder="选择租户连接" />
              </a-form-item>
              <a-form-item label="站点 URL">
                <a-input v-model:value="tenantMountForm.siteUrl" placeholder="https://tenant.sharepoint.cn/sites/od3" />
              </a-form-item>
              <a-form-item label="文档库名称">
                <a-input v-model:value="tenantMountForm.libraryName" placeholder="留空自动导入文档库" />
              </a-form-item>
              <a-form-item label="Root Path">
                <a-input v-model:value="tenantMountForm.rootPath" placeholder="/" />
              </a-form-item>
              <a-form-item>
                <a-checkbox v-model:checked="tenantMountForm.documentsOnly">只导入文档库</a-checkbox>
              </a-form-item>
              <a-button type="primary" html-type="submit" :loading="mountingTenantSite" block>挂载站点</a-button>
            </a-form>
          </a-card>
        </div>
      </a-tab-pane>

      <!-- Tab: SP 容量池 -->
      <a-tab-pane key="profiles" tab="SP 容量池">
        <div class="space-y-4">
        <a-card title="自动容量池" size="small">
          <div class="flex flex-col sm:flex-row gap-2 mb-3">
            <a-input
              v-model:value="capacityPoolForm.name"
              placeholder="输入容量池名称，例如 动漫池 / 电影池"
              @pressEnter="createCapacityPool"
            />
            <a-button type="primary" :loading="capacityPoolSaving" @click="createCapacityPool">新增容量池</a-button>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2">
            <div
              v-for="pool in capacityPoolCards"
              :key="pool.id"
              class="rounded-lg border border-border bg-surface p-3"
            >
              <div class="flex items-center justify-between gap-2 mb-2">
                <div class="font-semibold truncate">{{ pool.name }}</div>
                <a-space size="small">
                  <a-tag color="blue">{{ pool.profileCount }} 个 SP</a-tag>
                  <a-button size="small" @click="renameCapacityPool(pool.id, pool.name)">重命名</a-button>
                  <a-button
                    v-if="pool.id !== DEFAULT_CAPACITY_POOL_ID"
                    danger
                    size="small"
                    :disabled="pool.profileCount > 0"
                    @click="removeCapacityPool(pool.id)"
                  >删除</a-button>
                </a-space>
              </div>
              <div class="grid grid-cols-3 gap-2 text-xs text-text-muted">
                <div>
                  <div>已用</div>
                  <div class="font-medium text-text">{{ formatTb(pool.used) }}</div>
                </div>
                <div>
                  <div>剩余</div>
                  <div class="font-medium text-text">{{ formatTb(pool.remaining) }}</div>
                </div>
                <div>
                  <div>总量</div>
                  <div class="font-medium text-text">{{ formatTb(pool.total) }}</div>
                </div>
              </div>
            </div>
          </div>
        </a-card>
        <a-card title="已配置 SP" size="small">
          <a-alert
            type="info"
            show-icon
            class="mb-3"
            message="只有启用并加入容量池的 SP 会被自动上传、刷新容量和扫描目录；未启用的 SP 不会被这些自动流程修改或扫描。"
          />
          <div class="grid grid-cols-2 lg:grid-cols-4 gap-2 mb-3">
            <div class="rounded-lg border border-border bg-surface p-3">
              <div class="text-xs text-text-muted">启用 SP</div>
              <div class="text-xl font-semibold">{{ enabledProfiles.length }} / {{ store.state?.profiles.length || 0 }}</div>
            </div>
            <div class="rounded-lg border border-border bg-surface p-3">
              <div class="text-xs text-text-muted">已用容量</div>
              <div class="text-xl font-semibold">{{ formatTb(enabledQuotaUsed) }}</div>
            </div>
            <div class="rounded-lg border border-border bg-surface p-3">
              <div class="text-xs text-text-muted">剩余容量</div>
              <div class="text-xl font-semibold">{{ formatTb(enabledQuotaRemaining) }}</div>
            </div>
            <div class="rounded-lg border border-border bg-surface p-3">
              <div class="text-xs text-text-muted">总容量</div>
              <div class="text-xl font-semibold">{{ formatTb(enabledQuotaTotal) }}</div>
            </div>
          </div>
          <a-empty v-if="!store.state?.profiles.length" description="暂无 SP" />
          <ResponsiveTable
            v-else
            :columns="profileColumns"
            :data-source="store.state?.profiles || []"
            row-key="id" size="small" :pagination="{ pageSize: 10 }" :scroll="{ x: 940 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'name'"><span class="break-all">{{ record.name }}</span></template>
              <template v-if="column.key === 'quota'">
                <div class="min-w-[220px]">
                  <div class="text-xs mb-1">
                    <ProfileQuotaText :used="profileQuotaUsed(record)" :remaining="record.quotaRemaining" :total="record.quotaTotal" />
                  </div>
                  <a-progress
                    :percent="profileQuotaPercent(record)"
                    :show-info="false"
                    size="small"
                    :status="record.quotaState === 'full' ? 'exception' : 'normal'"
                  />
                </div>
              </template>
              <template v-if="column.key === 'capacity'">
                <a-switch
                  :checked="record.capacityEnabled !== false"
                  :loading="profileCapacityUpdating === record.id"
                  @change="onProfileCapacityChange(record.id, $event)"
                />
              </template>
              <template v-if="column.key === 'pool'">
                <a-select
                  :value="profilePoolId(record)"
                  :options="capacityPoolOptions"
                  :disabled="record.capacityEnabled === false"
                  :loading="profilePoolUpdating === record.id"
                  size="small"
                  class="min-w-[160px]"
                  @change="onProfilePoolSelect(record.id, $event)"
                />
              </template>
              <template v-if="column.key === 'action'">
                <a-button danger size="small" @click="removeProfile(record.id)">删除</a-button>
              </template>
            </template>
            <template #mobileCard="{ record }">
              <div class="flex items-start justify-between gap-2 mb-2">
                <div class="font-semibold text-sm min-w-0 break-all">{{ record.name }}</div>
                <a-tag :color="record.capacityEnabled !== false ? 'blue' : 'default'" class="shrink-0">
                  {{ record.capacityEnabled !== false ? '已启用' : '未启用' }}
                </a-tag>
              </div>
              <a-progress
                :percent="profileQuotaPercent(record)"
                :show-info="false"
                size="small"
                :status="record.quotaState === 'full' ? 'exception' : 'normal'"
                class="mb-2"
              />
              <div class="grid grid-cols-3 gap-2 text-xs mb-3">
                <div>
                  <div class="text-text-muted">已用</div>
                  <div class="font-medium">{{ formatTb(profileQuotaUsed(record)) }}</div>
                </div>
                <div>
                  <div class="text-text-muted">剩余</div>
                  <div class="font-medium">{{ formatTb(profileQuotaRemaining(record)) }}</div>
                </div>
                <div>
                  <div class="text-text-muted">总量</div>
                  <div class="font-medium">{{ formatTb(record.quotaTotal) }}</div>
                </div>
              </div>
              <div class="mb-3">
                <div class="text-xs text-text-muted mb-1">所属容量池</div>
                <a-select
                  :value="profilePoolId(record)"
                  :options="capacityPoolOptions"
                  :disabled="record.capacityEnabled === false"
                  :loading="profilePoolUpdating === record.id"
                  size="small"
                  class="w-full"
                  @change="onProfilePoolSelect(record.id, $event)"
                />
              </div>
              <div class="flex items-center justify-between gap-2">
                <a-space size="small">
                  <span class="text-xs text-text-muted">自动容量池</span>
                  <a-switch
                    size="small"
                    :checked="record.capacityEnabled !== false"
                    :loading="profileCapacityUpdating === record.id"
                    @change="onProfileCapacityChange(record.id, $event)"
                  />
                </a-space>
                <a-button danger size="small" @click="removeProfile(record.id)">删除</a-button>
              </div>
            </template>
          </ResponsiveTable>
        </a-card>
        </div>
      </a-tab-pane>

      <!-- Tab: 传输控制 -->
      <a-tab-pane key="transfer" tab="传输控制">
        <a-card title="每日上传限制" size="small">
          <a-form layout="vertical" :model="transferSettingsForm" @finish="saveTransferSettings">
            <a-form-item label="上传并发数">
              <a-input-number
                v-model:value="transferSettingsForm.transferConcurrency"
                :min="1"
                :max="16"
                :precision="0"
                addon-after="个任务"
                class="w-full"
              />
            </a-form-item>
            <a-form-item label="下载缓存目录">
              <a-space>
                <a-input v-model:value="transferSettingsForm.downloadDir" placeholder="留空使用默认目录" style="max-width: 400px; width: 100%" />
                <a-button @click="openDirBrowser">浏览...</a-button>
              </a-space>
              <div style="color: #888; font-size: 12px; margin-top: 4px">服务端本地路径，留空使用默认目录</div>
            </a-form-item>
            <a-form-item label="最小保留空间 (GB)">
              <a-input-number v-model:value="transferSettingsForm.minFreeSpaceGb" :min="0" :step="1" style="width: 120px" />
              <div style="color: #888; font-size: 12px; margin-top: 4px">磁盘可用空间低于此值暂停下载，设 0 不检查</div>
            </a-form-item>

            <a-form-item label="启用 Worker 模式">
              <a-switch v-model:checked="transferSettingsForm.workerMode" />
              <div style="color: #888; font-size: 12px; margin-top: 4px">开启后主控不再本地执行传输任务，仅通过 API 分配给远程 Worker (如 Android APP)</div>
            </a-form-item>

            <!-- 文件夹浏览弹窗 -->
            <a-modal v-model:open="dirBrowserOpen" title="选择服务端目录" :footer="null" width="550px">
              <div style="margin-bottom:8px;display:flex;align-items:center;justify-content:space-between">
                <div>
                  <a-button size="small" @click="goUpDir" :disabled="!dirBrowserParent">..</a-button>
                </div>
                <div v-if="dirBrowserFreeGb >= 0" :style="{color: dirBrowserFreeGb < 10 ? '#ff4d4f' : '#52c41a', fontSize:'12px', fontWeight:'bold'}">
                  剩余 {{ dirBrowserFreeGb.toFixed(1) }} GB
                </div>
              </div>
              <div style="margin-bottom:8px;font-family:monospace;font-size:12px;word-break:break-all;color:#555">{{ dirBrowserPath }}</div>
              <div v-if="dirBrowserError" style="color:#ff4d4f;margin-bottom:8px">{{ dirBrowserError }}</div>
              <a-spin :spinning="dirBrowserLoading">
                <div style="max-height:260px;overflow-y:auto;border:1px solid #d9d9d9;border-radius:4px">
                  <div v-if="dirBrowserDirs.length===0 && !dirBrowserError" style="padding:16px;color:#999;text-align:center">此目录下没有子文件夹</div>
                  <div v-for="d in dirBrowserDirs" :key="d.path" @click="enterDir(d.path)"
                       style="padding:8px 12px;cursor:pointer;border-bottom:1px solid #f0f0f0;display:flex;align-items:center"
                       @mouseenter="(e:any)=>e.target.style.background='#e6f7ff'" @mouseleave="(e:any)=>e.target.style.background=''">
                    <span style="margin-right:6px">📁</span>
                    <span style="font-size:13px">{{ d.name }}</span>
                  </div>
                </div>
              </a-spin>
              <div style="margin-top:8px;display:flex;gap:8px">
                <a-input v-model:value="newDirName" placeholder="新建文件夹名称" size="small" style="flex:1" @pressEnter="createNewDir" />
                <a-button size="small" @click="createNewDir" :loading="mkdirLoading">新建</a-button>
              </div>
              <div style="margin-top:12px;text-align:right">
                <a-button @click="dirBrowserOpen=false">取消</a-button>
                <a-button type="primary" style="margin-left:8px" @click="selectDirBrowser">选择此目录</a-button>
              </div>
            </a-modal>
            <a-form-item label="启用每日上传上限">
              <a-switch v-model:checked="transferSettingsForm.dailyUploadLimitEnabled" />
            </a-form-item>
            <a-form-item label="每日上传上限">
              <a-input-number
                v-model:value="transferSettingsForm.dailyUploadLimitGb"
                :min="0"
                :precision="2"
                addon-after="GB"
                class="w-full"
              />
            </a-form-item>
            <a-descriptions bordered size="small" :column="1" class="mb-3">
              <a-descriptions-item label="今日已完成上传">{{ formatSize(store.state?.stats?.todayUploaded?.totalSize || 0) }}</a-descriptions-item>
              <a-descriptions-item label="今日文件数">{{ store.state?.stats?.todayUploaded?.fileCount || 0 }} 个</a-descriptions-item>
            </a-descriptions>
            <a-button type="primary" html-type="submit" :loading="savingTransferSettings">保存设置</a-button>
          </a-form>
        </a-card>
      </a-tab-pane>

      <!-- Tab: 全局去重 -->
      <a-tab-pane key="dedupe" tab="全局去重">
        <div class="space-y-4">
          <a-card title="去重索引" size="small">
            <div class="flex gap-2 items-center justify-end mb-3">
              <a-button type="primary" :loading="findingDupes" @click="findDuplicates">查找重复</a-button>
              <a-button danger @click="clearDedupe">清空索引</a-button>
            </div>
            <a-descriptions bordered size="small" class="mb-3">
              <a-descriptions-item label="指纹总数">{{ store.state?.dedupe.count || 0 }}</a-descriptions-item>
              <a-descriptions-item label="重复组">{{ duplicateGroups.length }}</a-descriptions-item>
            </a-descriptions>

            <!-- 重复文件列表 -->
            <div v-if="duplicateGroups.length" class="space-y-3">
              <div
                v-for="group in duplicateGroups"
                :key="group.key"
                class="border border-red-200 rounded-lg p-3 bg-red-50"
              >
                <div class="flex items-center justify-between mb-2">
                  <span class="font-semibold text-sm text-red-700">
                    {{ formatSize(group.size) }} · {{ group.count }}份重复
                  </span>
                </div>
                <div class="space-y-1.5">
                  <div
                    v-for="(item, idx) in parseGroupItems(group)"
                    :key="idx"
                    class="flex items-center justify-between gap-2 bg-white rounded p-2 text-sm"
                  >
                    <div class="min-w-0 flex-1">
                      <div class="truncate text-gray-800">{{ item.file }}</div>
                      <div class="text-xs text-gray-400 truncate">{{ getProfileName(item.profileId) }} · {{ item.path }}</div>
                    </div>
                    <a-button
                      size="small"
                      danger
                      :loading="deletingItem === item.itemId"
                      @click="removeDuplicateFile(item)"
                    >删除</a-button>
                  </div>
                </div>
              </div>
            </div>
            <a-empty v-else-if="!findingDupes && scannedForDupes" description="没有重复文件" />
          </a-card>
          <a-card title="最新指纹" size="small">
            <a-table :columns="dedupeColumns" :data-source="store.state?.dedupe.latest || []" row-key="id" size="small" :scroll="{ x: 800 }">
              <template #bodyCell="{ column, record }">
                <template v-if="column.dataIndex === 'size'">{{ formatSize(record.size) }}</template>
              </template>
            </a-table>
          </a-card>
        </div>
      </a-tab-pane>

      <!-- Tab: 日志 -->
      <a-tab-pane key="logs" tab="日志">
        <a-card title="应用日志" size="small">
          <template #extra>
            <a-space>
              <a-select v-model:value="logLevel" :options="logLevelOpts" @change="loadLogs" class="w-24" size="small" />
              <a-button size="small" @click="loadLogs">刷新</a-button>
            </a-space>
          </template>
          <div class="bg-gray-900 text-gray-100 rounded-lg p-3 font-mono text-xs max-h-[60vh] overflow-y-auto leading-relaxed">
            <div v-if="!logs.length" class="text-gray-500">点击刷新加载日志</div>
            <div v-for="(entry, idx) in logs" :key="idx" :class="logColor(entry.level)">
              {{ entry.text }}
            </div>
          </div>
        </a-card>
      </a-tab-pane>

      <!-- Tab: 媒体目录 -->
      <a-tab-pane key="catalog" tab="媒体目录">
        <a-card title="SP 媒体目录扫描" size="small">
          <div class="flex gap-2 items-center justify-end mb-3">
            <a-button type="primary" :loading="store.state?.catalogScan.running" @click="scanCatalog">扫描已启用 SP</a-button>
          </div>
          <a-descriptions bordered size="small" :column="{ xs: 1, sm: 2 }">
            <a-descriptions-item label="状态">{{ store.state?.catalogScan.running ? '扫描中' : '空闲' }}</a-descriptions-item>
            <a-descriptions-item label="已扫描 SP">{{ store.state?.catalogScan.scannedProfiles || 0 }}</a-descriptions-item>
            <a-descriptions-item label="已扫描文件">{{ store.state?.catalogScan.scannedFiles || 0 }}</a-descriptions-item>
            <a-descriptions-item label="写入指纹">{{ store.state?.catalogScan.indexedFingerprints || 0 }}</a-descriptions-item>
            <a-descriptions-item label="清理指纹">{{ store.state?.catalogScan.removedFingerprints || 0 }}</a-descriptions-item>
            <a-descriptions-item label="最近错误">{{ store.state?.catalogScan.lastError || '-' }}</a-descriptions-item>
          </a-descriptions>
        </a-card>
      </a-tab-pane>
    </a-tabs>
  </a-card>

  <!-- 115 用户信息弹窗 -->
  <a-modal v-model:open="userInfoVisible" title="115 用户信息" :footer="null" width="400px">
    <a-descriptions v-if="userInfoData" bordered size="small" :column="1">
      <a-descriptions-item label="用户名">{{ userInfoData.userName }}</a-descriptions-item>
      <a-descriptions-item label="VIP">{{ userInfoData.vipName || '无' }}</a-descriptions-item>
      <a-descriptions-item label="已用空间">{{ userInfoData.spaceUsedFormat }}</a-descriptions-item>
      <a-descriptions-item label="总空间">{{ userInfoData.spaceTotalFormat }}</a-descriptions-item>
    </a-descriptions>
  </a-modal>

</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { message } from 'ant-design-vue';
import { useAppStore } from '../../stores/useAppStore';
import { tenantsApi } from '../../api/tenants';
import { oauthApi } from '../../api/oauth';
import { profilesApi } from '../../api/profiles';
import { capacityPoolsApi } from '../../api/capacity-pools';
import { dedupeApi } from '../../api/dedupe';
import { catalogApi } from '../../api/catalog';
import { pan115Api, type Pan115Account } from '../../api/pan115';
import { appSettingsApi, type Pan115ApiDelaySettings } from '../../api/settings';
import { request } from '../../api/request';
import ResponsiveTable from '../../components/common/ResponsiveTable.vue';
import ProfileQuotaText from '../../components/profiles/ProfileQuotaText.vue';
import type { CapacityPool, Profile } from '../../api/dashboard';

const store = useAppStore();
const tab = ref(localStorage.getItem('sjhl-settings-tab') || 'tenants');
const GB = 1024 * 1024 * 1024;
const DEFAULT_CAPACITY_POOL_ID = 'default';

function onTabChange(key: string) {
  localStorage.setItem('sjhl-settings-tab', key);
  if (key === 'logs') loadLogs();
}

const regionOpts = [{ label: '世纪互联', value: 'cn' }, { label: '全球', value: 'global' }];
const authModeOpts = [{ label: '应用权限', value: 'client_credentials' }, { label: 'Refresh Token', value: 'refresh_token' }];

// -- Tenants --
const tenantForm = reactive({ name: '', authMode: 'client_credentials', region: 'cn', tenantId: '', clientId: '', clientSecret: '', refreshToken: '', defaultRootPath: '/', importDocumentsOnly: true });
const tenantMountForm = reactive({ connectionId: '', siteUrl: '', libraryName: '', rootPath: '/', documentsOnly: true });
const tenantOAuthLoading = ref(false);
const mountingTenantSite = ref(false);
const tenantConnectionOptions = computed(() =>
  (store.state?.tenantConnections || []).map((item) => ({ label: item.name, value: item.id }))
);

async function startTenantOAuth() {
  tenantOAuthLoading.value = true;
  try {
    const body: any = { clientId: tenantForm.clientId || undefined };
    if (tenantForm.region) body.region = tenantForm.region;
    if (tenantForm.tenantId) body.tenantId = tenantForm.tenantId;
    if (tenantForm.clientSecret) body.clientSecret = tenantForm.clientSecret;
    if (tenantForm.defaultRootPath) body.rootPath = tenantForm.defaultRootPath;
    body.importDocumentsOnly = tenantForm.importDocumentsOnly;
    const r = await oauthApi.start(body);
    const w = window.open(r.authorizationUrl, 'sp-oauth', 'width=600,height=700');
    if (!w) { message.warning('请允许弹窗，或手动打开授权链接'); return; }
    message.info('请在弹窗中登录 Microsoft 授权');
    const timer = setInterval(async () => {
      if (w.closed) { clearInterval(timer); tenantOAuthLoading.value = false; message.info('授权窗口已关闭'); return; }
      try {
        const res = await oauthApi.result(r.state);
        if (res.result) {
          clearInterval(timer);
          w.close();
          message.success('授权成功，Token 已保存');
          store.loadState();
        }
      } catch (_) { /* 还没完成，继续轮询 */ }
    }, 2000);
  } catch (err) { store.showError(err); } finally { tenantOAuthLoading.value = false; }
}

async function submitTenant() { try { await tenantsApi.save(tenantForm); message.success('已保存'); store.loadState(); } catch (err) { store.showError(err); } }
async function importTenant(id: string) { try { const r = await tenantsApi.import(id); message.success(`已导入 ${r.count} 个`); store.loadState(); } catch (err) { store.showError(err); } }
async function removeTenant(id: string) { await tenantsApi.remove(id); store.loadState(); }
function selectMountTenant(id: string) { tenantMountForm.connectionId = id; }
async function mountTenantSite() {
  if (!tenantMountForm.connectionId) { store.showError(new Error('请选择租户连接')); return; }
  mountingTenantSite.value = true;
  try {
    const result = await tenantsApi.mountSharePoint(tenantMountForm.connectionId, {
      siteUrl: tenantMountForm.siteUrl,
      libraryName: tenantMountForm.libraryName,
      rootPath: tenantMountForm.rootPath,
      documentsOnly: tenantMountForm.documentsOnly,
    });
    message.success(`已挂载 ${result.count} 个文档库`);
    tenantMountForm.siteUrl = '';
    tenantMountForm.libraryName = '';
    await store.loadState();
  } catch (err) {
    store.showError(err);
  } finally {
    mountingTenantSite.value = false;
  }
}

// -- Pan115 Accounts --
const pan115Accounts = ref<Pan115Account[]>([]);
const pan115Form = reactive({ name: '', cookie: '', accessToken: '', refreshToken: '' });
const DEFAULT_OPEN_DELAY: Pan115ApiDelaySettings = {
  globalMultiplier: 1,
  globalDelaySeconds: 0.5,
  listDelaySeconds: 0.5,
  renameDelaySeconds: 0.5,
  deleteDelaySeconds: 0.5,
  mutateDelaySeconds: 0.5,
  downDelaySeconds: 0.5,
};
const DEFAULT_COOKIE_DELAY: Pan115ApiDelaySettings = {
  globalMultiplier: 1,
  globalDelaySeconds: 2,
  listDelaySeconds: 3,
  renameDelaySeconds: 1,
  deleteDelaySeconds: 2,
  mutateDelaySeconds: 1,
  downDelaySeconds: 0.5,
};
const pan115DelayMode = ref<'open' | 'cookie'>('open');
const pan115OpenDelayForm = reactive<Pan115ApiDelaySettings>({ ...DEFAULT_OPEN_DELAY });
const pan115CookieDelayForm = reactive<Pan115ApiDelaySettings>({ ...DEFAULT_COOKIE_DELAY });
const activePan115DelayForm = computed(() => (pan115DelayMode.value === 'open' ? pan115OpenDelayForm : pan115CookieDelayForm));
const savingPan115Delay = ref(false);

function normalizeDelay(settings: Partial<Pan115ApiDelaySettings> | undefined, defaults: Pan115ApiDelaySettings): Pan115ApiDelaySettings {
  const source = settings || {};
  return Object.fromEntries(
    Object.entries(defaults).map(([key, value]) => {
      const nextValue = Number((source as Record<string, unknown>)[key] ?? value);
      return [key, Number.isFinite(nextValue) ? Math.max(0, nextValue) : value];
    }),
  ) as Pan115ApiDelaySettings;
}

function assignDelay(target: Pan115ApiDelaySettings, source: Pan115ApiDelaySettings) {
  Object.assign(target, source);
}

function resetPan115Delay() {
  assignDelay(activePan115DelayForm.value, pan115DelayMode.value === 'open' ? { ...DEFAULT_OPEN_DELAY } : { ...DEFAULT_COOKIE_DELAY });
}

async function savePan115DelaySettings() {
  savingPan115Delay.value = true;
  try {
    await appSettingsApi.save({
      pan115OpenApiDelay: { ...pan115OpenDelayForm },
      pan115CookieApiDelay: { ...pan115CookieDelayForm },
    });
    message.success('115 API 延迟已保存');
    await loadTransferSettings();
  } catch (err) {
    store.showError(err);
  } finally {
    savingPan115Delay.value = false;
  }
}

async function load115Accounts() {
  try { const r = await pan115Api.listAccounts(); pan115Accounts.value = r.accounts; } catch (err) { store.showError(err); }
}

async function submit115Account() {
  try { await pan115Api.saveAccount(pan115Form); load115Accounts(); } catch (err) { store.showError(err); }
}

const authLoading = ref(false);

async function autoAuth115(accountId: string) {
  authLoading.value = true;
  try {
    const r = await pan115Api.clouddriveAutoAuth(accountId);
    await pan115Api.saveAccount({ id: accountId, accessToken: r.accessToken, refreshToken: r.refreshToken || '' });
    message.success('Open Token 获取成功，已自动保存！');
    load115Accounts();
  } catch (err) { store.showError(err); }
  finally { authLoading.value = false; }
}

async function remove115Account(id: string) {
  await pan115Api.removeAccount(id); load115Accounts();
}

// -- User info --
const userInfoVisible = ref(false);
const userInfoData = ref<any>(null);
const infoLoading = ref(false);

async function showUserInfo(accountId: string) {
  infoLoading.value = true;
  try {
    const r = await pan115Api.userInfo(accountId);
    userInfoData.value = r.info;
    userInfoVisible.value = true;
  } catch (err) { store.showError(err); }
  finally { infoLoading.value = false; }
}

// -- Profiles --
const profileColumns = [
  { title: '名称', key: 'name', width: 300 }, { title: '容量', key: 'quota', width: 260 },
  { title: '自动容量池', key: 'capacity', width: 120 },
  { title: '所属容量池', key: 'pool', width: 180 },
  { title: '操作', key: 'action', width: 100, fixed: 'right' }
];
const profileCapacityUpdating = ref('');
const profilePoolUpdating = ref('');
const capacityPoolSaving = ref(false);
const capacityPoolForm = reactive({ name: '' });
const enabledProfiles = computed(() =>
  (store.state?.profiles || []).filter((profile) => profile.capacityEnabled !== false)
);
const capacityPools = computed<CapacityPool[]>(() => {
  const pools = store.state?.capacityPools || [];
  if (pools.length) return pools;
  return [{ id: DEFAULT_CAPACITY_POOL_ID, name: '默认容量池', createdAt: '', updatedAt: '' }];
});
const capacityPoolOptions = computed(() =>
  capacityPools.value.map((pool) => ({ label: pool.name, value: pool.id }))
);
const capacityPoolCards = computed(() =>
  capacityPools.value.map((pool) => {
    const assignedProfiles = (store.state?.profiles || []).filter((profile) => profilePoolId(profile) === pool.id);
    const profiles = assignedProfiles.filter((profile) => profile.capacityEnabled !== false);
    return {
      ...pool,
      profileCount: assignedProfiles.length,
      total: profiles.reduce((sum, profile) => sum + Number(profile.quotaTotal || 0), 0),
      used: profiles.reduce((sum, profile) => sum + profileQuotaUsed(profile), 0),
      remaining: profiles.reduce((sum, profile) => sum + profileQuotaRemaining(profile), 0),
    };
  })
);
const enabledQuotaTotal = computed(() =>
  enabledProfiles.value.reduce((sum, profile) => sum + Number(profile.quotaTotal || 0), 0)
);
const enabledQuotaUsed = computed(() =>
  enabledProfiles.value.reduce((sum, profile) => sum + profileQuotaUsed(profile), 0)
);
const enabledQuotaRemaining = computed(() =>
  enabledProfiles.value.reduce((sum, profile) => sum + profileQuotaRemaining(profile), 0)
);
async function removeProfile(id: string) { await profilesApi.remove(id); store.loadState(); }
function profilePoolId(profile: Pick<Profile, 'capacityPoolId'>) {
  return profile.capacityPoolId || DEFAULT_CAPACITY_POOL_ID;
}
function onProfileCapacityChange(id: string, checked: unknown) {
  toggleProfileCapacity(id, Boolean(checked));
}
async function toggleProfileCapacity(id: string, enabled: boolean) {
  profileCapacityUpdating.value = id;
  try {
    await profilesApi.setCapacityEnabled(id, enabled);
    message.success(enabled ? '已加入自动容量池' : '已从自动容量池移除');
    await store.loadState();
  } catch (err) {
    store.showError(err);
  } finally {
    profileCapacityUpdating.value = '';
  }
}
async function createCapacityPool() {
  const name = capacityPoolForm.name.trim();
  if (!name) {
    store.showError(new Error('请填写容量池名称'));
    return;
  }
  capacityPoolSaving.value = true;
  try {
    await capacityPoolsApi.save({ name });
    capacityPoolForm.name = '';
    message.success('容量池已创建');
    await store.loadState();
  } catch (err) {
    store.showError(err);
  } finally {
    capacityPoolSaving.value = false;
  }
}
async function renameCapacityPool(id: string, currentName: string) {
  const name = window.prompt('请输入新的容量池名称', currentName)?.trim();
  if (!name || name === currentName) return;
  try {
    await capacityPoolsApi.save({ id, name });
    message.success('容量池名称已更新');
    await store.loadState();
  } catch (err) {
    store.showError(err);
  }
}
async function removeCapacityPool(id: string) {
  try {
    await capacityPoolsApi.remove(id);
    message.success('容量池已删除');
    await store.loadState();
  } catch (err) {
    store.showError(err);
  }
}
function onProfilePoolSelect(id: string, value: unknown) {
  onProfilePoolChange(id, String(value || DEFAULT_CAPACITY_POOL_ID));
}
async function onProfilePoolChange(id: string, poolId: string) {
  profilePoolUpdating.value = id;
  try {
    await profilesApi.setCapacityPool(id, poolId);
    message.success('SP 所属容量池已更新');
    await store.loadState();
  } catch (err) {
    store.showError(err);
  } finally {
    profilePoolUpdating.value = '';
  }
}
function profileQuotaUsed(profile: { quotaTotal?: number; quotaRemaining?: number; quotaUsed?: number }) {
  const used = Number(profile.quotaUsed || 0);
  if (used > 0) return used;
  return Math.max(0, Number(profile.quotaTotal || 0) - Number(profile.quotaRemaining || 0));
}
function profileQuotaRemaining(profile: { quotaTotal?: number; quotaRemaining?: number; quotaUsed?: number }) {
  const remaining = Number(profile.quotaRemaining || 0);
  if (remaining > 0) return remaining;
  return Math.max(0, Number(profile.quotaTotal || 0) - Number(profile.quotaUsed || 0));
}
function profileQuotaPercent(profile: { quotaTotal?: number; quotaRemaining?: number; quotaUsed?: number }) {
  const total = Number(profile.quotaTotal || 0);
  if (total <= 0) return 0;
  return Math.min(100, Math.round((profileQuotaUsed(profile) / total) * 100));
}
function formatTb(v: number) {
  if (!v) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let val = v, u = 0;
  while (val >= 1024 && u < units.length - 1) { val /= 1024; u++; }
  return `${val.toFixed(u === units.length - 1 ? 2 : val >= 10 || u === 0 ? 0 : 1)} ${units[u]}`;
}

// -- Dedupe --
const dedupeColumns = [{ title: '文件名', dataIndex: 'file_name', ellipsis: true }, { title: '大小', dataIndex: 'size' }, { title: 'SP', dataIndex: 'profile_id' }, { title: '路径', dataIndex: 'remote_path', ellipsis: true }];
const duplicateGroups = ref<Array<Record<string, any>>>([]);
const findingDupes = ref(false);
const scannedForDupes = ref(false);
const deletingItem = ref('');

async function findDuplicates() {
  findingDupes.value = true;
  try {
    const result = await dedupeApi.duplicates();
    duplicateGroups.value = result.groups || [];
    scannedForDupes.value = true;
  } catch (err) { store.showError(err); }
  finally { findingDupes.value = false; }
}

function parseGroupItems(group: Record<string, any>) {
  const files = String(group.files || '').split(',');
  const paths = String(group.paths || '').split(',');
  const profiles = String(group.profiles || '').split(',');
  const items = String(group.items || '').split(',');
  return files.map((file, i) => ({
    file, path: paths[i] || '', profileId: profiles[i] || '', itemId: items[i] || ''
  }));
}

function getProfileName(profileId: string) {
  const p = (store.state?.profiles || []).find((item) => item.id === profileId);
  return p?.name || profileId;
}

async function removeDuplicateFile(item: { profileId: string; itemId: string; file: string }) {
  if (!item.itemId || !item.profileId) return;
  deletingItem.value = item.itemId;
  try {
    await dedupeApi.deleteFile(item.profileId, item.itemId);
    await findDuplicates();
    store.loadState();
  } catch (err) { store.showError(err); }
  finally { deletingItem.value = ''; }
}

function formatSize(size: number) {
  if (!size) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = size, u = 0;
  while (v >= 1024 && u < units.length - 1) { v /= 1024; u++; }
  return `${v.toFixed(u === units.length - 1 ? 2 : v >= 10 || u === 0 ? 0 : 1)} ${units[u]}`;
}

// -- Transfer settings --
const transferSettingsForm = reactive({
  transferConcurrency: 4,
  dailyUploadLimitEnabled: false,
  dailyUploadLimitGb: 0,
  downloadDir: '',
  minFreeSpaceGb: 2,
  workerMode: false,
});
const savingTransferSettings = ref(false);

// -- Folder browser --
const dirBrowserOpen = ref(false);
const dirBrowserPath = ref('');
const dirBrowserParent = ref<string | null>(null);
const dirBrowserDirs = ref<{ name: string; path: string }[]>([]);
const dirBrowserLoading = ref(false);
const dirBrowserError = ref('');
const dirBrowserFreeGb = ref(-1);
const newDirName = ref('');
const mkdirLoading = ref(false);

async function browseDir(p: string) {
  dirBrowserLoading.value = true;
  dirBrowserError.value = '';
  try {
    const r = await request<{ ok: boolean; path: string; parent: string | null; dirs: { name: string; path: string }[]; error?: string; freeGb?: number }>(
      `/api/settings/browse-dir?path=${encodeURIComponent(p)}`
    );
    dirBrowserPath.value = r.path;
    dirBrowserParent.value = r.parent;
    dirBrowserDirs.value = r.dirs;
    dirBrowserFreeGb.value = r.freeGb ?? -1;
    if (r.error) dirBrowserError.value = r.error;
  } catch (e: any) {
    dirBrowserError.value = e?.message || String(e);
  } finally {
    dirBrowserLoading.value = false;
  }
}

function openDirBrowser() {
  dirBrowserOpen.value = true;
  newDirName.value = '';
  browseDir(transferSettingsForm.downloadDir || '');
}

function enterDir(p: string) { browseDir(p); }

function goUpDir() {
  if (dirBrowserParent.value) browseDir(dirBrowserParent.value);
}

function selectDirBrowser() {
  transferSettingsForm.downloadDir = dirBrowserPath.value;
  dirBrowserOpen.value = false;
}

async function createNewDir() {
  const name = newDirName.value.trim();
  if (!name) return;
  mkdirLoading.value = true;
  try {
    await request(`/api/settings/browse-dir/mkdir?path=${encodeURIComponent(dirBrowserPath.value)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    newDirName.value = '';
    await browseDir(dirBrowserPath.value);
  } catch (e: any) {
    dirBrowserError.value = e?.message || String(e);
  } finally {
    mkdirLoading.value = false;
  }
}

async function loadTransferSettings() {
  try {
    const r = await appSettingsApi.get();
    transferSettingsForm.transferConcurrency = Math.max(1, Number(r.settings.transferConcurrency || 4));
    transferSettingsForm.dailyUploadLimitEnabled = !!r.settings.dailyUploadLimitEnabled;
    transferSettingsForm.dailyUploadLimitGb = Number(((r.settings.dailyUploadLimitBytes || 0) / GB).toFixed(2));
    transferSettingsForm.downloadDir = r.settings.downloadDir || '';
    transferSettingsForm.minFreeSpaceGb = Number(r.settings.minFreeSpaceGb ?? 2);
    transferSettingsForm.workerMode = !!r.settings.workerMode;
    assignDelay(pan115OpenDelayForm, normalizeDelay(r.settings.pan115OpenApiDelay, DEFAULT_OPEN_DELAY));
    assignDelay(pan115CookieDelayForm, normalizeDelay(r.settings.pan115CookieApiDelay, DEFAULT_COOKIE_DELAY));
  } catch (err) {
    store.showError(err);
  }
}

async function saveTransferSettings() {
  savingTransferSettings.value = true;
  try {
    await appSettingsApi.save({
      transferConcurrency: Math.max(1, Math.round(Number(transferSettingsForm.transferConcurrency || 4))),
      dailyUploadLimitEnabled: transferSettingsForm.dailyUploadLimitEnabled,
      dailyUploadLimitBytes: Math.max(0, Math.round((transferSettingsForm.dailyUploadLimitGb || 0) * GB)),
      downloadDir: transferSettingsForm.downloadDir.trim(),
      minFreeSpaceGb: Math.max(0, Math.round(transferSettingsForm.minFreeSpaceGb || 2)),
      workerMode: transferSettingsForm.workerMode,
    });
    message.success('传输设置已保存');
    await Promise.all([loadTransferSettings(), store.loadState()]);
  } catch (err) {
    store.showError(err);
  } finally {
    savingTransferSettings.value = false;
  }
}

async function clearDedupe() { try { await dedupeApi.clear(); store.loadState(); duplicateGroups.value = []; scannedForDupes.value = false; } catch (err) { store.showError(err); } }

// -- Logs --
const logs = ref<Array<{ text: string; level: string }>>([]);
const logLevel = ref('');
const logLevelOpts = [
  { label: '全部', value: '' }, { label: 'DEBUG', value: 'DEBUG' },
  { label: 'INFO', value: 'INFO' }, { label: 'WARNING', value: 'WARNING' }, { label: 'ERROR', value: 'ERROR' },
];

async function loadLogs() {
  try {
    const r = await request<{ ok: true; logs: Array<{ text: string; level: string }> }>(`/api/logs?level=${logLevel.value}&lines=500`);
    logs.value = [...(r.logs || [])].reverse();
  } catch (err) { store.showError(err); }
}

function logColor(level: string) {
  return level === 'ERROR' ? 'text-red-400' : level === 'WARNING' ? 'text-yellow-400' : level === 'DEBUG' ? 'text-gray-500' : 'text-green-300';
}

// -- Catalog --
async function scanCatalog() { try { await catalogApi.scan(); store.loadState(); } catch (err) { store.showError(err); } }

onMounted(() => { load115Accounts(); loadTransferSettings(); if (tab.value === 'logs') loadLogs(); });
</script>
