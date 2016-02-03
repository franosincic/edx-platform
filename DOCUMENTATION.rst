TASK: Adding temporary user

GOAL: Temporary user will obtain a staff member access for a predefined period of time, default seven days. In that time this user can make a new course and edit it. After expiration date this user will be erased via celery task job. 

common/djangoapps/student/models.py
- Added two new fields, temp_users and expiry_date.

common/djangoapps/student/migrations/0002_auto_20151218_0826.py
- Migrations for Student.

cms/envs/common.py
- Added two new features, EXPIRY_DATE_DEFAULT and ENABLE_TEMP_USER.

common/djangoapps/student/views.py
- Added a new view for registering temp users.
- Added a new method, get_temp_user_enable_status for checking is feature of temp users enabled.
- Modified _do_create_account, create_account_with_params and create_account for saving temp user profile, activating his account and prevent his immediately logging in.

cms/urls.py
- Added new urls.

cms/templates/index.html
- Added two new links, New Temp User and Temp Users list.

cms/templates/register_temp_user.html
- New template for registering temp users, has a field temp_user.

cms/templates/temp_users_home.html
- New template for listing all temp users, their courses and libraries. Also provides link for deleting their content.

cms/djangoapps/contentstore/views/course.py
- Added new method _get_temp_user_creator_status, returns a temp users creator permission.
- Added new view, temp_users_home_handler. This view fetch all temp users and then their courses(via get_courses_accessible_to_user method) and libraries(via accessible_libraries_list method).
- Added views for deleting temp user, his courses and libraries.
- Some methods from this file were moved in helpers.py.

cms/djangoapps/contentstore/helpers.py
- This methods were moved here beacuse of dependecied failures.
- Methods got a new argument, this_user and check if that argument exist, because the request argument is from staff user, and with this methods we want to fetch data of some particular user.
- Method _accessible_libraries_list is renamed to accessible_libraries_list.
- Some other method were also moved to this file just because dependecies.
- Methods format_course_for_view and format_library_for_view are now independent methods.

common/lib/xmodule/xmodule/modulestore/django.py
- Added three new signals deleted_course, deleted_library and deleted_temp_user.

cms/djangoapps/contentstore/signals.py
- Added three new recevier for signals. Every signal calls it's task.

cms/djangoapps/contentstore/tasks.py
- Added three new tasks.
- Task delete_course_task is responsible for deleting temp users courses. It calls delete_course_and_groups method and based on course and user id deletes the course. Also removes course from elastic search. 
- Task delete_library_task is responsible for deleting temp users libraries. 
- Task delete_temp_user_task is responsible for deleting all of temp users courses and libraries(we delete only his content because deleting of temp user is not enabled).

cms/djangoapps/contentstore/tests/test_course_listing.py
- Only imports were modified because some methods were moved to another file.

TO DO:
- View temps_user_home is not needed. It was made because of testing, deleting temp users is not planned to be manually done.
- Views, signals and tasks for deleting course and library are not needed, it can be done via just delete temp user view, signal and task.
- Make a celery periodic task for deleting temporary user.
