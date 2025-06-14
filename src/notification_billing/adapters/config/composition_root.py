from dependency_injector import containers, providers

container = None

def setup_di_container_from_settings(settings):  # noqa: PLR0915
    """Inicializa o DI container após o Django já estar com settings carregados."""
    global container  # noqa: PLW0603
    if container is not None:
        import structlog
        structlog.get_logger().debug("DI container já inicializado.")
        return container

    # ------- IMPORTS DE INFRA E ADAPTERS -------
    import redis
    import structlog

    # API client, mappers e infra de mensageria...
    from oralsin_core.adapters.repositories.address_repo_impl import AddressRepoImpl
    from oralsin_core.adapters.repositories.contract_repo_impl import ContractRepoImpl
    from oralsin_core.adapters.repositories.installment_repo_impl import InstallmentRepoImpl
    from oralsin_core.adapters.repositories.patient_repo_impl import PatientRepoImpl
    from oralsin_core.core.domain.mappers.oralsin_payload_mapper import OralsinPayloadMapper

    # Mensageria e notificadores
    from notification_billing.adapters.message_broker.rabbitmq import RabbitMQ
    from notification_billing.adapters.notifiers.registry import get_notifier

    # Repositórios concretos (Django ORM)
    from notification_billing.adapters.repositories.contact_history_repo_impl import ContactHistoryRepoImpl
    from notification_billing.adapters.repositories.contact_schedule_repo_impl import ContactScheduleRepoImpl
    from notification_billing.adapters.repositories.flow_step_config_repo_impl import FlowStepConfigRepoImpl
    from notification_billing.adapters.repositories.message_repo_impl import MessageRepoImpl
    from notification_billing.adapters.repositories.pending_call_repo_impl import PendingCallRepoImpl

    # ------- IMPORTS DO CORE DE NOTIFICATION_BILLING -------
    # Commands
    from notification_billing.core.application.commands.contact_commands import (
        AdvanceContactStepCommand,
        RecordContactSentCommand,
    )
    from notification_billing.core.application.commands.contact_schedule_commands import (
        CreateContactScheduleCommand,
        DeleteContactScheduleCommand,
        UpdateContactScheduleCommand,
    )
    from notification_billing.core.application.commands.message_commands import (
        CreateMessageCommand,
        DeleteMessageCommand,
        UpdateMessageCommand,
    )
    from notification_billing.core.application.commands.notification_commands import (
        RunAutomatedNotificationsCommand,
        SendManualNotificationCommand,
    )
    from notification_billing.core.application.commands.pending_call_commands import SetPendingCallDoneCommand
    from notification_billing.core.application.commands.sync_commands import (
        BulkScheduleContactsCommand,
    )

    # CQRS
    from notification_billing.core.application.cqrs import CommandBusImpl, QueryBusImpl

    # Handlers
    from notification_billing.core.application.handlers.contact_handlers import (
        AdvanceContactStepHandler,
        RecordContactSentHandler,
    )
    from notification_billing.core.application.handlers.core_entities_handlers import (
        CreateContactScheduleHandler,
        CreateMessageHandler,
        DeleteContactScheduleHandler,
        DeleteMessageHandler,
        UpdateContactScheduleHandler,
        UpdateMessageHandler,
    )
    from notification_billing.core.application.handlers.list_pending_schedules_handler import ListPendingSchedulesHandler
    from notification_billing.core.application.handlers.notification_handlers import (
        NotificationSenderService,
        RunAutomatedNotificationsHandler,
        SendManualNotificationHandler,
    )
    from notification_billing.core.application.handlers.pending_call_handlers import GetPendingCallHandler, ListPendingCallsHandler, SetPendingCallDoneHandler
    from notification_billing.core.application.handlers.sync_handlers import BulkScheduleContactsHandler

    # Queries
    from notification_billing.core.application.queries.notification_queries import ListPendingSchedulesQuery
    from notification_billing.core.application.queries.pending_call_queries import GetPendingCallQuery, ListPendingCallsQuery
    from notification_billing.core.application.services.contact_service import ContactSchedulingService

    # Serviços de aplicação
    from notification_billing.core.application.services.formatter_service import FormatterService
    from notification_billing.core.application.services.notification_service import NotificationFacadeService

    # Event Dispatcher
    from notification_billing.core.domain.services.event_dispatcher import EventDispatcher

    # ------- DECLARAÇÃO DO CONTAINER -------
    class Container(containers.DeclarativeContainer):
        config = providers.Configuration()

        # Infra & integração
        logger           = providers.Singleton(structlog.get_logger)
        event_dispatcher = providers.Singleton(EventDispatcher)

        # CQRS
        command_bus = providers.Singleton(CommandBusImpl, dispatcher=event_dispatcher)
        query_bus   = providers.Singleton(QueryBusImpl)

        # Redis, RabbitMQ, Notifier Registry
        rabbit            = providers.Singleton(RabbitMQ, url=config.rabbitmq_url)
        redis_client      = providers.Singleton(
                                redis.Redis,
                                host=config.redis.host,
                                port=config.redis.port,
                                db=config.redis.db,
                                password=config.redis.password,
                            )
        notifier_registry = providers.Object(get_notifier)

        # Implementações de Repositórios (Ports → Adapters)
        address_repo        = providers.Singleton(AddressRepoImpl)
        oralsin_mapper      = providers.Singleton(OralsinPayloadMapper)
        flow_step_config_repo   = providers.Singleton(FlowStepConfigRepoImpl)
        message_repo            = providers.Singleton(MessageRepoImpl)
        contact_history_repo    = providers.Singleton(ContactHistoryRepoImpl)
        contract_repo           = providers.Singleton(ContractRepoImpl)
        installment_repo        = providers.Singleton(
            InstallmentRepoImpl,
            mapper=oralsin_mapper,
        )
        contact_schedule_repo   = providers.Singleton(
            ContactScheduleRepoImpl,
            installment_repo=installment_repo,
        )
        patient_repo            = providers.Singleton(
            PatientRepoImpl,
            address_repo=address_repo
        )
        pending_call_repo   = providers.Singleton(PendingCallRepoImpl)

        # Serviços de negócio
        formatter_service        = providers.Singleton(FormatterService, currency_symbol="R$")
        notification_sender_service = providers.Singleton(
                                          NotificationSenderService,
                                          message_repo=message_repo,
                                          patient_repo=patient_repo,
                                          installment_repo=installment_repo,
                                      )

        contact_scheduling_service = providers.Singleton(
            ContactSchedulingService,
            schedule_repo=contact_schedule_repo,
            installment_repo=installment_repo,
            flow_cfg_repo=flow_step_config_repo,
            dispatcher=event_dispatcher,
        )
        # Facade exposto aos controllers/CLI
        notification_facade_service = providers.Singleton(
                                          NotificationFacadeService,
                                          command_bus=command_bus,
                                          query_bus=query_bus,
                                      )
        notification_service = notification_facade_service

        # Handlers CRUD
        list_pending_schedules_handler = providers.Factory(
            ListPendingSchedulesHandler,
            schedule_repo=contact_schedule_repo,
        )
        create_message_handler = providers.Factory(
            CreateMessageHandler,
            repo=message_repo,
        )
        update_message_handler = providers.Factory(
            UpdateMessageHandler,
            repo=message_repo,
        )
        delete_message_handler = providers.Factory(
            DeleteMessageHandler,
            repo=message_repo,
        )
        create_contact_schedule_handler = providers.Factory(
            CreateContactScheduleHandler,
            repo=contact_schedule_repo,
        )
        update_contact_schedule_handler = providers.Factory(
            UpdateContactScheduleHandler,
            repo=contact_schedule_repo,
        )
        delete_contact_schedule_handler = providers.Factory(
            DeleteContactScheduleHandler,
            repo=contact_schedule_repo,
        )

        # Handlers de fluxo de contato/notificação
        advance_contact_step_handler = providers.Factory(
            AdvanceContactStepHandler,
            schedule_repo=contact_schedule_repo,
            dispatcher=event_dispatcher,
        )
        record_contact_sent_handler = providers.Factory(
            RecordContactSentHandler,
            schedule_repo=contact_schedule_repo,
            history_repo=contact_history_repo,
            dispatcher=event_dispatcher,
        )

        # Handlers de notificação
        send_manual_notification_handler = providers.Factory(
            SendManualNotificationHandler,
            schedule_repo=contact_schedule_repo,
            history_repo=contact_history_repo,
            notification_service=notification_sender_service,
            pending_call_repo=pending_call_repo,
            dispatcher=event_dispatcher,
        )
        run_automated_notifications_handler = providers.Factory(
            RunAutomatedNotificationsHandler,
            config_repo=flow_step_config_repo,
            schedule_repo=contact_schedule_repo,
            history_repo=contact_history_repo,
            pending_call_repo=pending_call_repo,
            notification_service=notification_sender_service,
            dispatcher=event_dispatcher,
            query_bus=query_bus,
        )

        # Handlers de sync (inadimplência)
        advance_contact_step_handler = providers.Factory(
            AdvanceContactStepHandler,
            schedule_repo=contact_schedule_repo,
            dispatcher=event_dispatcher,
        )
        
        bulk_schedule_contacts_handler = providers.Factory(
            BulkScheduleContactsHandler,
            contract_repo=contract_repo,
            installment_repo=installment_repo,
            schedule_repo=contact_schedule_repo,
            config_repo=flow_step_config_repo,
            pending_call_repo=pending_call_repo,
            dispatcher=event_dispatcher,
            logger=logger(),  
        )
        list_pending_calls_handler = providers.Factory(
            ListPendingCallsHandler, repo=pending_call_repo
        )
        get_pending_call_handler = providers.Factory(
            GetPendingCallHandler, repo=pending_call_repo
        )
        set_pending_call_done_handler = providers.Factory(
            SetPendingCallDoneHandler, 
            repo=pending_call_repo, 
            history_repo=contact_history_repo,
            schedule_repo=contact_schedule_repo,
            dispatcher=event_dispatcher
        )

        def init(self):
            # Registrar comandos no CommandBus
            bus = self.command_bus()

            # ContactSchedule CRUD
            bus.register(CreateContactScheduleCommand, self.create_contact_schedule_handler())
            bus.register(UpdateContactScheduleCommand, self.update_contact_schedule_handler())
            bus.register(DeleteContactScheduleCommand, self.delete_contact_schedule_handler())

            # Message CRUD
            bus.register(CreateMessageCommand, self.create_message_handler())
            bus.register(UpdateMessageCommand, self.update_message_handler())
            bus.register(DeleteMessageCommand, self.delete_message_handler())

            # Contact Flow / Notificações
            bus.register(AdvanceContactStepCommand, self.advance_contact_step_handler())
            bus.register(RecordContactSentCommand, self.record_contact_sent_handler())
            bus.register(SendManualNotificationCommand, self.send_manual_notification_handler())
            bus.register(RunAutomatedNotificationsCommand, self.run_automated_notifications_handler())
            bus.register(BulkScheduleContactsCommand, self.bulk_schedule_contacts_handler())

            bus.register(
                SetPendingCallDoneCommand, self.set_pending_call_done_handler()
            )
                        
            # Registrar queries no QueryBus
            qb = self.query_bus()
            qb.register(ListPendingSchedulesQuery, self.list_pending_schedules_handler())

            
            qb.register(
                ListPendingCallsQuery, self.list_pending_calls_handler()
            )
            qb.register(
                GetPendingCallQuery, self.get_pending_call_handler()
            )
    # ------- INSTANCIAÇÃO E CONFIG -------
    container = Container()
    container.config.rabbitmq_url.from_value(settings.RABBITMQ_URL)
    container.config.redis.host.from_value(settings.REDIS_HOST)
    container.config.redis.port.from_value(settings.REDIS_PORT)
    container.config.redis.db.from_value(settings.REDIS_DB)
    container.config.redis.password.from_value(settings.REDIS_PASSWORD)

    # Inicializa o CommandBus com todos os handlers
    Container.init(container)
    return container
