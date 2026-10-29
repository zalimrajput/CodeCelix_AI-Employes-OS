# from pydantic import BaseModel
# from uuid import UUID


# class UserCreate(BaseModel):

#     organization_id:UUID

#     full_name:str

#     email:str

#     password:str



# class UserResponse(BaseModel):

#     id:UUID

#     organization_id:UUID

#     full_name:str

#     email:str

#     status:str


#     class Config:

#         from_attributes=True






from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime


class UserCreate(BaseModel):

    organization_id: UUID

    full_name: str | None = None

    email: EmailStr

    password: str

    phone: str | None = None

    # Optional role name to assign (e.g. "Sales Manager", "Customer Support").
    # No role is assigned when omitted.
    role_name: str | None = None



class UserResponse(BaseModel):

    id: UUID

    organization_id: UUID

    full_name: str | None

    email: str

    avatar_url: str | None

    phone: str | None

    status: str

    created_at: datetime

    updated_at: datetime


    model_config = {
        "from_attributes": True
    }