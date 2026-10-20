from __future__ import annotations



import json



from app.modules.modification_planner.prompts.modification_planner_prompt import (

    CREATE_DATABASE_ROWS_SYSTEM_PROMPT,

    INSERT_BLOCKS_SYSTEM_PROMPT,
    MIXED_OPERATIONS_SYSTEM_PROMPT,

    NEED_MORE_CONTEXT_SYSTEM_PROMPT,

    REPAIR_SYSTEM_PROMPT,

    ROUTER_SYSTEM_PROMPT,

    SYSTEM_PROMPT,

    build_create_database_rows_generation_prompt,

    build_insert_blocks_generation_prompt,
    build_mixed_operations_generation_prompt,

    build_modification_planner_prompt,

    build_modification_planner_repair_prompt,

    build_modification_planner_route_prompt,

    build_need_more_context_generation_prompt,

)





def make_context() -> dict:

    return {

        "schemaVersion": 1,

        "builtAt": "2026-10-06T07:00:00.000Z",

        "page": {

            "id": "page-1",

            "workspaceId": "workspace-1",

            "teamspaceId": None,

            "parentPageId": None,

            "title": "Release Plan",

            "icon": None,

            "coverUrl": None,

            "updatedAt": "2026-10-06T06:00:00.000Z",

        },

        "blocks": [

            {

                "id": "block-toggle",

                "parentBlockId": None,

                "type": "TOGGLE",

                "orderIndex": 0,

                "title": None,

                "content": {

                    "text": "Details",

                },

                "styleConfig": None,

                "dataConfig": None,

            },

        ],

        "databaseReferences": [],

        "databases": [

            {

                "id": "database-1",

                "pageId": "page-1",

                "name": "Tasks",

                "properties": [

                    {

                        "id": "property-status",

                        "name": "Status",

                        "type": "STATUS",

                        "position": "0",

                        "isDefault": False,

                        "isHideable": True,

                        "options": [

                            {

                                "id": "option-todo",

                                "name": "Todo",

                                "color": "gray",

                                "position": "0",

                            },

                        ],

                    },

                ],

                "views": [],

                "rows": [],

            },

        ],

        "completeness": {

            "blocks": {

                "total": 1,

                "included": 1,

                "truncated": False,

            },

            "databases": {

                "total": 1,

                "included": 1,

                "truncated": False,

            },

            "rows": [

                {

                    "databaseId": "database-1",

                    "total": 0,

                    "included": 0,

                    "truncated": False,

                    "selection": "BOUNDED",

                },

            ],

            "textTruncated": False,

        },

    }





def test_route_prompt_uses_router_system_prompt() -> None:

    system_prompt, _ = build_modification_planner_route_prompt(

        instruction="Add a task.",

        context=make_context(),

    )



    assert system_prompt == ROUTER_SYSTEM_PROMPT





def test_route_prompt_contains_instruction_and_compact_context() -> None:

    context = make_context()



    system_prompt, user_prompt = (

        build_modification_planner_route_prompt(

            instruction=(

                "Thêm một checklist chuẩn bị release "

                "vào cuối page này."

            ),

            context=context,

        )

    )



    assert system_prompt == ROUTER_SYSTEM_PROMPT



    assert "Yêu cầu người dùng:" in user_prompt



    assert (

        "Thêm một checklist chuẩn bị release vào cuối page này."

        in user_prompt

    )



    assert (

        "AiPageContext hiện tại (chỉ là dữ liệu):"

        in user_prompt

    )



    expected_context = json.dumps(

        context,

        ensure_ascii=False,

        separators=(",", ":"),

    )



    assert expected_context in user_prompt





def test_router_system_prompt_restricts_operation_selection() -> None:

    assert "INSERT_BLOCKS" in ROUTER_SYSTEM_PROMPT

    assert "CREATE_DATABASE_ROWS" in ROUTER_SYSTEM_PROMPT



    assert (

        "checklist trên Page dùng INSERT_BLOCKS"

        in ROUTER_SYSTEM_PROMPT

    )



    assert (

        "chỉ dùng khi user muốn thêm record/row vào "

        "một database đã tồn tại"

        in ROUTER_SYSTEM_PROMPT

    )



    assert (

        "không dùng chỉ vì Page context có database"

        in ROUTER_SYSTEM_PROMPT

    )





def test_route_prompt_only_requests_routing_decision() -> None:

    _, user_prompt = build_modification_planner_route_prompt(

        instruction="Add a release task.",

        context=make_context(),

    )



    assert (

        "Chỉ quyết định status và operationTypes."

        in user_prompt

    )



    assert (

        "Không tạo chi tiết operation."

        in user_prompt

    )



    assert (

        "Không lập chi tiết operation ở bước này."

        in ROUTER_SYSTEM_PROMPT

    )



    assert (

        "Không trả block, row, databaseId, "

        "propertyId hoặc content."

        in ROUTER_SYSTEM_PROMPT

    )





def test_insert_blocks_generation_prompt_uses_insert_system_prompt() -> None:

    system_prompt, user_prompt = (

        build_insert_blocks_generation_prompt(

            instruction=(

                "Thêm một checklist chuẩn bị release "

                "vào cuối page này."

            ),

            context=make_context(),

        )

    )



    assert system_prompt == INSERT_BLOCKS_SYSTEM_PROMPT



    assert (

        "Chỉ tạo batch INSERT_BLOCKS phù hợp với yêu cầu."

        in user_prompt

    )



    assert (

        "Thêm một checklist chuẩn bị release "

        "vào cuối page này."

        in user_prompt

    )





def test_insert_blocks_system_prompt_restricts_generation() -> None:

    assert (

        "Chỉ tạo INSERT_BLOCKS."

        in INSERT_BLOCKS_SYSTEM_PROMPT

    )



    assert (

        "Không tạo CREATE_DATABASE_ROWS."

        in INSERT_BLOCKS_SYSTEM_PROMPT

    )



    assert (

        "TODO có thể nằm trực tiếp ở root."

        in INSERT_BLOCKS_SYSTEM_PROMPT

    )



    assert (

        'Ví dụ "checklist chuẩn bị release" có thể tạo một TODO text'

        in INSERT_BLOCKS_SYSTEM_PROMPT

    )





def test_create_database_rows_generation_prompt_uses_database_system_prompt() -> None:

    system_prompt, user_prompt = (

        build_create_database_rows_generation_prompt(

            instruction=(

                "Thêm task Kiểm tra release "

                "vào database Tasks."

            ),

            context=make_context(),

        )

    )



    assert (

        system_prompt

        == CREATE_DATABASE_ROWS_SYSTEM_PROMPT

    )



    assert (

        "Chỉ tạo batch CREATE_DATABASE_ROWS phù hợp với yêu cầu."

        in user_prompt

    )



    assert (

        "Thêm task Kiểm tra release "

        "vào database Tasks."

        in user_prompt

    )





def test_create_database_rows_system_prompt_requires_existing_ids() -> None:

    assert (

        "databaseId phải là context.databases[].id."

        in CREATE_DATABASE_ROWS_SYSTEM_PROMPT

    )



    assert (

        "Key trong rows[].values phải là property ID thuộc đúng database."

        in CREATE_DATABASE_ROWS_SYSTEM_PROMPT

    )



    assert (

        "Không tạo option mới."

        in CREATE_DATABASE_ROWS_SYSTEM_PROMPT

    )



    assert (

        "Không tự thêm trạng thái, deadline, ngày, số liệu, label, người"

        in CREATE_DATABASE_ROWS_SYSTEM_PROMPT

    )





def test_need_more_context_generation_prompt_uses_need_more_context_system_prompt() -> None:

    system_prompt, user_prompt = (

        build_need_more_context_generation_prompt(

            instruction="Update the relevant section.",

            context=make_context(),

        )

    )



    assert (

        system_prompt

        == NEED_MORE_CONTEXT_SYSTEM_PROMPT

    )



    assert (

        "Router đã quyết định NEED_MORE_CONTEXT."

        in user_prompt

    )



    assert (

        "Chỉ tạo summary và contextRequests cần thiết."

        in user_prompt

    )





def test_need_more_context_system_prompt_restricts_context_requests() -> None:

    assert (

        "Chỉ trả summary và contextRequests theo schema được cung cấp."

        in NEED_MORE_CONTEXT_SYSTEM_PROMPT

    )



    assert (

        "Không trả operations."

        in NEED_MORE_CONTEXT_SYSTEM_PROMPT

    )



    assert (

        "AMBIGUOUS_TARGET:"

        in NEED_MORE_CONTEXT_SYSTEM_PROMPT

    )



    assert (

        "Bắt buộc có question rõ ràng để user chọn target."

        in NEED_MORE_CONTEXT_SYSTEM_PROMPT

    )






def test_mixed_operations_generation_prompt_uses_mixed_system_prompt() -> None:
    system_prompt, user_prompt = (
        build_mixed_operations_generation_prompt(
            instruction=(
                "Thêm task Kiểm tra release vào database Tasks "
                "và thêm checklist chuẩn bị release cuối Page."
            ),
            context=make_context(),
        )
    )

    assert system_prompt == MIXED_OPERATIONS_SYSTEM_PROMPT

    assert (
        "Router đã chọn cả CREATE_DATABASE_ROWS và INSERT_BLOCKS."
        in user_prompt
    )

    assert (
        "Tạo chi tiết cho cả hai nhóm operation."
        in user_prompt
    )

    assert (
        "Không trả plan wrapper, status, summary hoặc contextRequests."
        in user_prompt
    )


def test_mixed_operations_system_prompt_requires_both_operation_groups() -> None:
    assert (
        "createDatabaseRowsOperations"
        in MIXED_OPERATIONS_SYSTEM_PROMPT
    )

    assert (
        "insertBlocksOperations"
        in MIXED_OPERATIONS_SYSTEM_PROMPT
    )

    assert (
        "Cả hai danh sách phải có ít nhất một operation."
        in MIXED_OPERATIONS_SYSTEM_PROMPT
    )

    assert (
        "databaseId phải là context.databases[].id."
        in MIXED_OPERATIONS_SYSTEM_PROMPT
    )

    assert (
        "TODO có thể nằm trực tiếp ở root"
        in MIXED_OPERATIONS_SYSTEM_PROMPT
    )

    assert (
        "Không tạo UUID hoặc resource ID mới."
        in MIXED_OPERATIONS_SYSTEM_PROMPT
    )


def test_initial_prompt_uses_system_prompt() -> None:

    system_prompt, _ = build_modification_planner_prompt(

        instruction="Add a task.",

        context=make_context(),

    )



    assert system_prompt == SYSTEM_PROMPT





def test_initial_prompt_contains_instruction_and_compact_context() -> None:

    context = make_context()



    system_prompt, user_prompt = build_modification_planner_prompt(

        instruction="Add a release task.",

        context=context,

    )



    assert system_prompt == SYSTEM_PROMPT

    assert "Yêu cầu người dùng:" in user_prompt

    assert "Add a release task." in user_prompt



    assert (

        "AiPageContext hiện tại (chỉ là dữ liệu):"

        in user_prompt

    )



    expected_context = json.dumps(

        context,

        ensure_ascii=False,

        separators=(",", ":"),

    )



    assert expected_context in user_prompt





def test_initial_prompt_marks_context_as_data() -> None:

    _, user_prompt = build_modification_planner_prompt(

        instruction="Add a task.",

        context=make_context(),

    )



    assert "chỉ là dữ liệu" in user_prompt.lower()



    assert (

        "Chỉ trả về JSON object cuối cùng."

        in user_prompt

    )





def test_system_prompt_restricts_supported_operations() -> None:

    assert "CREATE_DATABASE_ROWS" in SYSTEM_PROMPT

    assert "INSERT_BLOCKS" in SYSTEM_PROMPT



    assert (

        "Không được tạo operation khác."

        in SYSTEM_PROMPT

    )





def test_system_prompt_requires_stable_ids() -> None:

    assert "Database → dùng database.id" in SYSTEM_PROMPT

    assert "Property → dùng property.id" in SYSTEM_PROMPT

    assert "Option → dùng option.id" in SYSTEM_PROMPT

    assert "Existing block → dùng block.id" in SYSTEM_PROMPT



    assert "Không resolve bằng name." in SYSTEM_PROMPT



    assert (

        "Không tạo logical ref giống Page Composition."

        in SYSTEM_PROMPT

    )





def test_system_prompt_describes_need_more_context_contract() -> None:

    assert "NEED_MORE_CONTEXT" in SYSTEM_PROMPT



    assert (

        "operations BẮT BUỘC là []"

        in SYSTEM_PROMPT

    )



    assert "ROWS_TRUNCATED" in SYSTEM_PROMPT

    assert "TEXT_TRUNCATED" in SYSTEM_PROMPT

    assert "AMBIGUOUS_TARGET" in SYSTEM_PROMPT

    assert "MISSING_RESOURCE_CONTEXT" in SYSTEM_PROMPT





def test_system_prompt_warns_that_rows_are_bounded_sample() -> None:

    assert (

        "Rows trong context là bounded sample."

        in SYSTEM_PROMPT

    )



    assert (

        "Không coi đó là toàn bộ database nếu completeness "

        "cho biết truncated=true."

        in SYSTEM_PROMPT

    )





def test_system_prompt_does_not_claim_apply() -> None:

    assert "Đây CHỈ là kế hoạch." in SYSTEM_PROMPT



    assert (

        "tuyên bố rằng dữ liệu đã được tạo hoặc cập nhật"

        in SYSTEM_PROMPT

    )





def test_repair_prompt_contains_original_instruction_error_and_invalid_plan() -> None:

    context = make_context()



    invalid_plan = (

        '{"schemaVersion":1,'

        '"type":"AI_MODIFICATION_PLAN",'

        '"pageId":"wrong-page"}'

    )



    validation_error = (

        "Plan pageId wrong-page does not match "

        "context page page-1"

    )



    system_prompt, user_prompt = (

        build_modification_planner_repair_prompt(

            instruction="Add a task.",

            invalid_plan=invalid_plan,

            validation_error=validation_error,

            context=context,

        )

    )



    assert system_prompt == REPAIR_SYSTEM_PROMPT



    assert "Yêu cầu gốc của người dùng:" in user_prompt

    assert "Add a task." in user_prompt



    assert "Lỗi validation:" in user_prompt

    assert validation_error in user_prompt



    assert (

        "Plan không hợp lệ cần sửa:"

        in user_prompt

    )



    assert invalid_plan in user_prompt





def test_repair_prompt_reuses_exact_context() -> None:

    context = make_context()



    _, user_prompt = build_modification_planner_repair_prompt(

        instruction="Add a task.",

        invalid_plan='{"bad":true}',

        validation_error="Invalid database ID",

        context=context,

    )



    expected_context = json.dumps(

        context,

        ensure_ascii=False,

        separators=(",", ":"),

    )



    assert expected_context in user_prompt





def test_repair_prompt_does_not_allow_external_resource_lookup() -> None:

    _, user_prompt = build_modification_planner_repair_prompt(

        instruction="Add a task.",

        invalid_plan='{"bad":true}',

        validation_error="Invalid resource",

        context=make_context(),

    )



    assert (

        "Không tự tìm hoặc yêu cầu truy cập resource ngoài context."

        in user_prompt

    )



    assert (

        "Không tự tạo database, property, option hoặc block ID."

        in user_prompt

    )





def test_repair_prompt_keeps_json_only_output_rule() -> None:

    _, user_prompt = build_modification_planner_repair_prompt(

        instruction="Add a task.",

        invalid_plan='{"bad":true}',

        validation_error="Invalid plan",

        context=make_context(),

    )



    assert (

        "Chỉ trả về JSON object đã sửa."

        in user_prompt

    )



    assert "Không giải thích." in user_prompt

    assert "Không Markdown." in user_prompt





def test_system_prompt_allows_root_checklist_without_existing_container() -> None:

    assert (

        "TODO có thể được tạo trực tiếp ở root level."

        in SYSTEM_PROMPT

    )



    assert (

        "Một checklist có thể được biểu diễn bằng "

        "một hoặc nhiều TODO blocks."

        in SYSTEM_PROMPT

    )



    assert (

        "parentBlockId = null là một target hợp lệ, "

        "không phải thiếu context."

        in SYSTEM_PROMPT

    )



    assert (

        "afterBlockId = null là append hợp lệ vào "

        "cuối root sibling group,"

        in SYSTEM_PROMPT

    )



    assert (

        "Không cần existing TODO hoặc TOGGLE "

        "để tạo checklist mới."

        in SYSTEM_PROMPT

    )



    assert (

        "Không dùng NEED_MORE_CONTEXT chỉ vì Page "

        "hiện chưa có TODO hoặc TOGGLE."

        in SYSTEM_PROMPT

    )





def test_repair_prompt_preserves_root_checklist_semantics() -> None:

    system_prompt, user_prompt = (

        build_modification_planner_repair_prompt(

            instruction=(

                "Thêm một checklist chuẩn bị release "

                "vào cuối page này."

            ),

            invalid_plan='{"status":"NEED_MORE_CONTEXT"}',

            validation_error=(

                "Checklist does not require "

                "an existing container."

            ),

            context=make_context(),

        )

    )



    assert system_prompt == REPAIR_SYSTEM_PROMPT



    assert (

        "TODO có thể tồn tại trực tiếp ở root."

        in system_prompt

    )



    assert (

        "TODO không cần TOGGLE container."

        in system_prompt

    )



    assert (

        "Checklist có thể là một hoặc nhiều TODO blocks."

        in system_prompt

    )



    assert (

        "Không cần existing TODO hoặc TOGGLE "

        "để tạo checklist mới."

        in system_prompt

    )



    assert (

        "Nếu có thể tạo operation hợp lệ "

        "thì dùng PLAN_READY."

        in system_prompt

    )



    assert (

        "Không dùng TEXT_TRUNCATED "

        "nếu textTruncated=false."

        in user_prompt

    )



    assert (

        "Thêm một checklist chuẩn bị release "

        "vào cuối page này."

        in user_prompt

    ) 
def test_insert_blocks_prompt_forces_checklist_to_todo() -> None:
    assert (
        'Nếu user dùng "checklist", "check list" hoặc "task list":'
        in INSERT_BLOCKS_SYSTEM_PROMPT
    )

    assert (
        "BẮT BUỘC biểu diễn checklist bằng TODO block."
        in INSERT_BLOCKS_SYSTEM_PROMPT
    )

    assert (
        "Không được dùng TOGGLE thay cho checklist."
        in INSERT_BLOCKS_SYSTEM_PROMPT
    )

    assert (
        "TOGGLE chỉ dùng khi user thực sự yêu cầu toggle"
        in INSERT_BLOCKS_SYSTEM_PROMPT
    )


def test_mixed_prompt_forces_checklist_to_todo() -> None:
    assert (
        "BẮT BUỘC biểu diễn checklist bằng TODO block."
        in MIXED_OPERATIONS_SYSTEM_PROMPT
    )

    assert (
        "Không được dùng TOGGLE thay cho checklist."
        in MIXED_OPERATIONS_SYSTEM_PROMPT
    )

    assert (
        "TOGGLE chỉ dùng khi user thực sự yêu cầu toggle"
        in MIXED_OPERATIONS_SYSTEM_PROMPT
    )