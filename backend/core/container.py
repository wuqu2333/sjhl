from __future__ import annotations

from dataclasses import dataclass

from config.settings import DATA_DIR, TRANSFER_CONCURRENCY
from core.database import AppDatabase
from crud.dedupe import DedupeStore
from crud.profiles import ProfileStore
from crud.sync_jobs import SyncStore
from crud.tenants import TenantStore
from crud.transfers import TransferJobStore
from app.stores import AppSettingsStore, CapacityPoolStore, Pan115AccountStore
from services.capacity import CapacityService
from services.catalog import CatalogService
from services.discovery import TenantDiscoveryService
from services.graph import GraphClient
from services.oauth import OAuthService
from services.pan115 import Pan115Client
from services.sync_engine import SyncEngine
from services.transfer_queue import JobQueue


@dataclass
class AppContainer:
    database: AppDatabase
    profiles: ProfileStore
    tenants: TenantStore
    sync_store: SyncStore
    dedupe: DedupeStore
    graph: GraphClient
    pan115: Pan115Client
    capacity: CapacityService
    capacity_pools: CapacityPoolStore
    transfer_jobs: TransferJobStore
    jobs: JobQueue
    catalog: CatalogService
    discovery: TenantDiscoveryService
    sync_engine: SyncEngine
    oauth: OAuthService
    pan115_accounts: Pan115AccountStore
    app_settings: AppSettingsStore


def build_container() -> AppContainer:
    database = AppDatabase(DATA_DIR)
    profiles = ProfileStore(DATA_DIR)
    tenants = TenantStore(DATA_DIR)
    sync_store = SyncStore(DATA_DIR)
    dedupe = DedupeStore(database)
    graph = GraphClient(
        on_refresh_token=lambda record_id, token: (
            profiles.update_refresh_token(record_id, token),
            tenants.update_refresh_token(record_id, token),
        )
    )
    app_settings = AppSettingsStore(DATA_DIR)
    pan115 = Pan115Client(settings_store=app_settings)
    capacity_pools = CapacityPoolStore(DATA_DIR)
    capacity = CapacityService(profiles, graph, capacity_pools)
    transfer_jobs = TransferJobStore(database)
    pan115_accounts = Pan115AccountStore(DATA_DIR)
    jobs = JobQueue(profiles, dedupe, graph, capacity, transfer_jobs, pan115, TRANSFER_CONCURRENCY, app_settings, pan115_accounts)
    catalog = CatalogService(profiles, graph, dedupe)
    discovery = TenantDiscoveryService(tenants, profiles, graph)
    sync_engine = SyncEngine(sync_store, profiles, graph, pan115, jobs, dedupe)
    sync_engine.pan115_accounts = pan115_accounts
    oauth = OAuthService(profiles, tenants)
    return AppContainer(
        database=database,
        profiles=profiles,
        tenants=tenants,
        sync_store=sync_store,
        dedupe=dedupe,
        graph=graph,
        pan115=pan115,
        capacity=capacity,
        capacity_pools=capacity_pools,
        transfer_jobs=transfer_jobs,
        jobs=jobs,
        catalog=catalog,
        discovery=discovery,
        sync_engine=sync_engine,
        oauth=oauth,
        pan115_accounts=pan115_accounts,
        app_settings=app_settings,
    )


container = build_container()


def get_container() -> AppContainer:
    return container
